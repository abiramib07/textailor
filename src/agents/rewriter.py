"""Rewriter agent — tailors each resume section's LaTeX content to a job
description's missing keywords and action verbs, one Claude call per section.
"""

import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

log = logging.getLogger("textailor.rewriter")

_PROMPT = """You are an expert resume writer specialising in ATS-optimised LaTeX resumes.

Your task: rewrite the LaTeX content for ONE section below.

RULES:
1. Rewrite bullet points using Google XYZ formula: "Accomplished [X], as measured by [Y], by doing [Z]"
2. Weave in the MISSING KEYWORDS naturally — do not stuff them; they must fit contextually
3. Mirror the JD's ACTION VERBS where possible (use them to start bullets)
4. Never invent metrics or experience — if a bullet has no measurable result, improve language only
   and mark it by appending " %NEEDS_METRIC" AFTER the bullet command's closing brace, never before
   it: \\bulletitem{{Improved onboarding flow.}} %NEEDS_METRIC — putting it inside the braces (e.g.
   \\bulletitem{{...text. %NEEDS_METRIC}}) is a bug: the unescaped % starts a LaTeX comment right
   there, silently swallowing the closing brace and breaking compilation
5. Preserve ALL LaTeX commands exactly: \\item[], \\textbf{{}}, \\hfill, \\vspace{{}}, \\begin{{itemize}}, etc.
6. Only modify the human-readable text INSIDE \\item[] blocks and section prose
7. Do NOT touch the structure, spacing commands, or custom macros
8. ESCAPE these characters in all plain text: & → \\& (P\\&L not P&L), % → \\% (except comment lines starting with %), # → \\#
9. CRITICAL — never remove or reword any technology name, tool, platform, or skill that already
   appears in the ORIGINAL content below, even if it isn't in the MISSING KEYWORDS list. You may
   ONLY ADD the missing keywords on top of what's already there — do not drop or paraphrase away
   an existing one to make room. The candidate is already getting ATS credit for every keyword
   currently present; silently losing one is worse than failing to add a new one.
10. Output ONLY the rewritten LaTeX section content — no markers, no explanation, no markdown fences,
    no notes, no tables, and no commentary about your choices anywhere before, inside, or after the
    LaTeX. Your entire response must be valid LaTeX and nothing else — it gets inserted directly into
    the .tex file and compiled as-is.

MISSING KEYWORDS TO INCORPORATE (only if contextually honest):
{keywords}

JD ACTION VERBS TO USE:
{verbs}

SECTION TO REWRITE ({name}):
{content}
"""


def _escape_ampersands(tex: str) -> str:
    return re.sub(r"(?<!\\)&", r"\\&", tex)


def _looks_like_rewritten_latex(original: str, candidate: str) -> tuple[bool, str]:
    """Reject a Claude response that reads as conversational commentary
    rather than actual rewritten LaTeX resume content.

    The prompt (rule 10) demands LaTeX-only output, but rule 4 ("never
    invent metrics or experience") and "only if contextually honest" on
    keywords create a genuine conflict when the JD's missing keywords
    describe a domain the candidate has no experience in — Claude
    sometimes resolves that conflict by explaining the concern in prose
    instead of complying with rule 10. Nothing downstream validates the
    response before splicing it into the .tex file, so unchecked prose
    silently replaces real resume content and still compiles (LaTeX
    tolerates plain text). Two independent, low-false-positive signals:
    resume content never poses a question to the reader, and a rewrite is
    required to preserve every existing LaTeX command (rule 9) — dropping
    all of them is only plausible if the response isn't LaTeX at all.
    """
    if "?" in candidate:
        return (
            False,
            "the response contains a question mark — resume content never asks the reader a question",
        )
    original_commands = set(re.findall(r"\\([a-zA-Z]+)", original))
    candidate_commands = set(re.findall(r"\\([a-zA-Z]+)", candidate))
    if original_commands and not candidate_commands:
        return False, "the response dropped every LaTeX command present in the original section"
    return True, ""


def _strip_leaked_commentary(tex: str) -> str:
    """The prompt tells Claude to output ONLY LaTeX, but it sometimes still
    appends a trailing explanation of its choices (e.g. a "Notes on keyword
    placement" markdown table). That leaks literal markdown into the .tex
    file and can break compilation outright — a backtick-quoted `\\item` in
    a table cell, for instance, reads to LaTeX as a real \\item outside any
    list environment. Truncate at the first sign of markdown creeping in,
    since valid LaTeX content here never starts a line with "|" or "**".
    """
    lines = tex.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith("|")
            or re.match(r"^-{3,}$", stripped)
            or re.match(r"^\*\*notes\b", stripped, re.IGNORECASE)
            or re.match(r"^notes on\b", stripped, re.IGNORECASE)
        ):
            cut_lines = len(lines) - i
            if cut_lines > 0:
                log.warning(
                    "Truncated %d trailing line(s) of leaked commentary "
                    "(triggered by: %r) — verify this wasn't real content",
                    cut_lines,
                    stripped[:60],
                )
            return "\n".join(lines[:i]).rstrip()
    return tex


def _rewrite_section(name: str, content: str, keywords: list, verbs: list) -> tuple[str, str]:
    """Return (content, warning) — `warning` is "" unless Claude's response
    failed the LaTeX-content validation, in which case `content` is the
    original, unmodified section and `warning` explains why to the caller."""
    prompt = _PROMPT.format(
        name=name,
        content=content,
        keywords="\n".join(f"- {kw}" for kw in keywords),
        verbs=", ".join(verbs),
    )
    t_start = time.monotonic()
    raw = ask_claude(prompt)
    elapsed = time.monotonic() - t_start
    cleaned = _strip_leaked_commentary(raw.strip())
    result = _escape_ampersands(cleaned.strip())

    ok, reason = _looks_like_rewritten_latex(content, result)
    if not ok:
        log.warning(
            "  %s: rejected Claude's response — %s. Keeping original section unchanged. "
            "Raw response: %r",
            name,
            reason,
            raw[:500],
        )
        warning = (
            f'Kept the original "{name}" content unchanged — the AI declined to weave in '
            f"the requested keywords honestly ({reason}) rather than fabricate matching "
            "experience. Review the missing keywords for this section manually."
        )
        return content, warning

    log.info(
        "  %s: %d chars in -> %d chars raw -> %d chars final (%.1fs)",
        name,
        len(content),
        len(raw),
        len(result),
        elapsed,
    )
    if len(result) < len(content) * 0.5:
        log.warning(
            "  %s: rewritten content is less than half the length of the original "
            "(%d -> %d chars) — likely truncated or over-compressed",
            name,
            len(content),
            len(result),
        )
    return result, ""


def rewrite(
    sections: dict,
    priority_keywords: list,
    key_action_verbs: list,
    sections_to_rewrite: list | None = None,
) -> tuple[dict, list[str]]:
    """Call Claude once per section, in parallel, to avoid timeout on large
    prompts and to avoid paying each section's Claude CLI cold-start cost
    sequentially — sections are independent of each other, so a
    ThreadPoolExecutor collapses wall-clock time to roughly the slowest
    single section instead of the sum of all of them.

    Returns (rewritten_sections, warnings) — `warnings` lists any section
    kept unchanged because Claude's response failed content validation
    (see `_looks_like_rewritten_latex`), so callers can surface this to the
    end user instead of it disappearing silently. Both the result dict's
    key order and the warnings list order match `sections_to_rewrite`'s
    order, not completion order, so callers see the same deterministic
    ordering the previous sequential implementation produced.
    """
    if sections_to_rewrite is None:
        sections_to_rewrite = [k for k in sections if k != "Education"]

    # Filter to sections that actually exist, then dedupe (first
    # occurrence wins the position) — a duplicate name must not trigger a
    # wasted extra Claude call.
    seen: set[str] = set()
    names: list[str] = []
    for name in sections_to_rewrite:
        if name in sections and name not in seen:
            seen.add(name)
            names.append(name)

    if not names:
        return {}, []

    def _run(name: str) -> tuple[str, str]:
        log.info("rewriting section: %s (%d keywords to weave in)", name, len(priority_keywords))
        return _rewrite_section(name, sections[name], priority_keywords, key_action_verbs)

    result: dict[str, str] = {}
    warning_map: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(names)) as executor:
        futures = {executor.submit(_run, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                content, warning = future.result()
                result[name] = content
                if warning:
                    warning_map[name] = warning
                log.info("done: %s", name)
            except Exception:
                log.exception("%s failed — keeping original section unchanged", name)
                result[name] = sections[name]

    ordered_result = {name: result[name] for name in names}
    warnings = [warning_map[name] for name in names if name in warning_map]
    return ordered_result, warnings


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.recruiter import analyze
    from latex_parser import parse_resume

    sample_jd = """
    AI/ML Engineer — Bangalore (Hybrid)
    Requirements:
    - Python, PyTorch, TensorFlow
    - Fine-tuning LLMs (LoRA, QLoRA, PEFT)
    - RAG pipelines using LangChain or LlamaIndex
    - Vector databases: Pinecone, Weaviate, Chroma
    - FastAPI REST API development
    - Prompt engineering and LLM evaluation techniques
    - Git, Docker, Azure
    Nice to have:
    - LangGraph, multi-agent frameworks
    - MLOps, CI/CD for ML pipelines
    - AWS
    """

    resume_data = parse_resume()
    recruiter_result = analyze(sample_jd, resume_data["plain_text"])

    print("Running Rewriter Agent ...\n")
    result, warnings = rewrite(
        sections=resume_data["sections"],
        priority_keywords=recruiter_result["priority_adds"],
        key_action_verbs=recruiter_result["key_action_verbs"],
        sections_to_rewrite=["Career Objective", "Experience", "Skills"],
    )

    for name, content in result.items():
        print(f"\n{'=' * 60}")
        print(f"SECTION: {name}")
        print("=" * 60)
        print(content[:800])

    if warnings:
        print(f"\n{'=' * 60}\nWARNINGS\n{'=' * 60}")
        for w in warnings:
            print(f"- {w}")
