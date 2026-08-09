"""Tests for parallelizing the per-section Claude calls in
agents.rewriter.rewrite() — see
docs/design-plans/2026-08-09-parallel-section-rewrite.md.

Written and run against the *pre-change* sequential implementation first
(the `for name in sections_to_rewrite:` loop calling `ask_claude` once per
section, one at a time) to confirm the concurrency-proving tests genuinely
fail there, before the ThreadPoolExecutor implementation exists. Every
test in this file must still pass afterward, alongside the unmodified
tests/test_rewriter_validation.py suite (no regression to the
leaked-commentary rejection logic, which this change doesn't touch).
"""

import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import rewriter  # noqa: E402

_NAME_RE = re.compile(r"SECTION TO REWRITE \((.+?)\):")


def _section_name_from_prompt(prompt: str) -> str:
    """Recover which section a fake ask_claude call was made for, by
    parsing it back out of the real prompt template rewriter.py builds."""
    match = _NAME_RE.search(prompt)
    assert match, "prompt did not contain a recognizable section name"
    return match.group(1)


_SECTIONS = {
    "Career Objective": "Original career objective content.",
    "Experience": "Original experience content.",
    "Projects": "Original projects content.",
    "Skills": "Original skills content.",
}


class TestConcurrency:
    """Prove sections genuinely run in parallel, not just that the
    function still returns the right thing. A wall-clock threshold
    assertion (e.g. "total time < sum of delays") would be flaky under
    CI/CPU contention, so instead each fake call records its own
    (start, end) monotonic interval and the test asserts a real pairwise
    overlap between two of them — only possible if both were in flight
    at the same time, independent of absolute timing."""

    def test_two_sections_overlap_in_time(self, monkeypatch) -> None:
        intervals: list[tuple[str, float, float]] = []
        lock = threading.Lock()

        def fake_ask_claude(prompt: str) -> str:
            name = _section_name_from_prompt(prompt)
            start = time.monotonic()
            time.sleep(0.3)
            end = time.monotonic()
            with lock:
                intervals.append((name, start, end))
            return _SECTIONS[name] + " rewritten"

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=["Python"],
            key_action_verbs=["Built"],
            sections_to_rewrite=list(_SECTIONS.keys()),
        )

        assert len(intervals) == len(_SECTIONS)
        overlap_found = False
        for i in range(len(intervals)):
            for j in range(i + 1, len(intervals)):
                _, a_start, a_end = intervals[i]
                _, b_start, b_end = intervals[j]
                if a_start < b_end and b_start < a_end:
                    overlap_found = True
        assert overlap_found, (
            "no two sections' Claude calls overlapped in time — "
            "rewrite() is still running sections sequentially"
        )


class TestResultOrdering:
    """Completion order is nondeterministic once calls run concurrently —
    the returned dict's key order must still match sections_to_rewrite's
    order, not whichever fake call happened to finish first."""

    def test_result_order_matches_sections_to_rewrite_despite_reversed_completion(
        self, monkeypatch
    ) -> None:
        order = ["Career Objective", "Experience", "Projects", "Skills"]
        # Delays deliberately decrease down the list, so completion order
        # is the exact reverse of `order`.
        delays = {
            "Career Objective": 0.4,
            "Experience": 0.3,
            "Projects": 0.2,
            "Skills": 0.1,
        }

        def fake_ask_claude(prompt: str) -> str:
            name = _section_name_from_prompt(prompt)
            time.sleep(delays[name])
            return _SECTIONS[name] + " rewritten"

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        result, _warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=order,
        )

        assert list(result.keys()) == order


class TestWarningsOrdering:
    """Same ordering guarantee for the warnings list."""

    def test_warnings_order_matches_sections_to_rewrite_not_completion_order(
        self, monkeypatch
    ) -> None:
        order = ["Career Objective", "Experience", "Projects"]
        delays = {"Career Objective": 0.3, "Experience": 0.2, "Projects": 0.1}

        def fake_ask_claude(prompt: str) -> str:
            name = _section_name_from_prompt(prompt)
            time.sleep(delays[name])
            # A "?" in the response triggers _looks_like_rewritten_latex's
            # rejection path, producing a warning for this section.
            return f"Are you sure about {name}?"

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        _result, warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=order,
        )

        assert len(warnings) == len(order)
        for name, warning in zip(order, warnings, strict=True):
            assert f'"{name}"' in warning


class TestExceptionIsolation:
    """One section's Claude call raising must not affect any other
    section's result, and must not abort collection of results for
    sections whose futures already completed — mirrors the existing
    sequential except/log.exception fallback behavior."""

    def test_one_section_exception_does_not_affect_others(self, monkeypatch) -> None:
        order = ["Career Objective", "Experience", "Projects"]

        def fake_ask_claude(prompt: str) -> str:
            name = _section_name_from_prompt(prompt)
            if name == "Experience":
                time.sleep(0.2)
                raise RuntimeError("simulated Claude CLI failure")
            return _SECTIONS[name] + " rewritten"

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        result, _warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=order,
        )

        assert result["Experience"] == _SECTIONS["Experience"]
        assert result["Career Objective"] == _SECTIONS["Career Objective"] + " rewritten"
        assert result["Projects"] == _SECTIONS["Projects"] + " rewritten"


class TestEmptyInput:
    """sections_to_rewrite can legitimately be empty (config-driven) —
    must return cleanly, not raise ThreadPoolExecutor(max_workers=0)."""

    def test_empty_sections_to_rewrite_returns_empty_without_raising(self, monkeypatch) -> None:
        def fake_ask_claude(prompt: str) -> str:
            raise AssertionError("ask_claude should not be called when there's nothing to rewrite")

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        result, warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=[],
        )
        assert result == {}
        assert warnings == []

    def test_names_not_in_sections_are_filtered_to_empty(self, monkeypatch) -> None:
        def fake_ask_claude(prompt: str) -> str:
            raise AssertionError("ask_claude should not be called")

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        result, warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=["Nonexistent Section"],
        )
        assert result == {}
        assert warnings == []


class TestDuplicateNames:
    """A duplicate name in sections_to_rewrite must not trigger a wasted
    extra Claude call per occurrence, and must appear once in the result."""

    def test_duplicate_section_name_calls_ask_claude_once(self, monkeypatch) -> None:
        call_count: dict[str, int] = {}

        def fake_ask_claude(prompt: str) -> str:
            name = _section_name_from_prompt(prompt)
            call_count[name] = call_count.get(name, 0) + 1
            return _SECTIONS[name] + " rewritten"

        monkeypatch.setattr(rewriter, "ask_claude", fake_ask_claude)

        result, _warnings = rewriter.rewrite(
            sections=_SECTIONS,
            priority_keywords=[],
            key_action_verbs=[],
            sections_to_rewrite=["Career Objective", "Career Objective", "Experience"],
        )

        assert call_count["Career Objective"] == 1
        assert list(result.keys()) == ["Career Objective", "Experience"]
