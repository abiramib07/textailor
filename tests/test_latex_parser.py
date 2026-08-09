"""Regression tests for `strip_latex()` — a bug silently deleted the content
of this template's structural macros (`\\bulletitem`, `\\bulletpoints`,
`\\techline`, `\\projectheading`) and everything after an escaped `\\%` on a
line, instead of keeping the human-readable text. Both fed straight into the
recruiter/scorer agents, so the ATS score was computed against a resume
missing nearly all of its Experience section.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from latex_parser import strip_latex  # noqa: E402


class TestStructuralMacrosSurvive:
    """Each of this template's custom macros must unwrap to its inner text,
    not be deleted wholesale."""

    def test_bulletitem_keeps_its_text(self):
        assert strip_latex(r"\bulletitem{Built a RAG pipeline.}") == "Built a RAG pipeline."

    def test_bulletpoints_keeps_its_bulletitems(self):
        tex = r"\bulletpoints{\bulletitem{First achievement.}\bulletitem{Second achievement.}}"
        result = strip_latex(tex)
        assert "First achievement." in result
        assert "Second achievement." in result

    def test_techline_keeps_its_tech_list(self):
        assert "Python, FastAPI, LangChain" in strip_latex(
            r"\techline{Python, FastAPI, LangChain}"
        )

    def test_projectheading_keeps_its_title(self):
        assert strip_latex(r"\projectheading{AI Analytics Platform}") == "AI Analytics Platform"

    def test_jobheading_keeps_all_four_fields(self):
        result = strip_latex(
            r"\jobheading{Generative AI Developer}{Acme Corp}{Remote}{Jan 2024 -- Present}"
        )
        assert "Generative AI Developer" in result
        assert "Acme Corp" in result
        assert "Remote" in result
        assert "Jan 2024" in result

    def test_skillrow_keeps_category_and_items(self):
        result = strip_latex(r"\skillrow{AI Frameworks}{LangChain, LangGraph}")
        assert "AI Frameworks" in result
        assert "LangChain, LangGraph" in result

    def test_bulletitem_with_nested_textbf_unwraps_both_layers(self):
        result = strip_latex(r"\bulletitem{Built \textbf{RAG} pipelines end-to-end.}")
        assert result == "Built RAG pipelines end-to-end."

    def test_full_bulletpoints_block_with_nested_formatting(self):
        """Mirrors the actual structure in resume/main.tex: bulletpoints
        wrapping multiple bulletitems, one containing nested \\textbf."""
        tex = (
            r"\bulletpoints{"
            r"\bulletitem{Shipped a \textbf{production} RAG chatbot.}"
            r"\bulletitem{Reduced latency by 40 percent.}"
            r"}"
        )
        result = strip_latex(tex)
        assert "Shipped a production RAG chatbot." in result
        assert "Reduced latency by 40 percent." in result


class TestEscapedPercentSurvives:
    """An escaped \\% is real content (a metric), not a LaTeX comment marker
    — only a bare, unescaped % should truncate the rest of the line."""

    def test_text_after_escaped_percent_is_preserved(self):
        result = strip_latex(r"\bulletitem{Achieved 85\% answer relevance across 200+ queries.}")
        assert result == "Achieved 85% answer relevance across 200+ queries."

    def test_multiple_escaped_percents_in_one_bullet(self):
        result = strip_latex(
            r"\bulletitem{Cut latency 40\% and improved accuracy 60\% in the same release.}"
        )
        assert "40%" in result
        assert "60%" in result
        assert "same release" in result

    def test_genuine_comment_line_is_still_stripped(self):
        """A real LaTeX comment (unescaped %, typically at line start) must
        still be removed — the fix only protects the escaped \\% case."""
        result = strip_latex("% === EXPERIENCE ===\n\\bulletitem{Real content here.}")
        assert "EXPERIENCE" not in result
        assert "Real content here." in result


class TestFullResumeIntegration:
    """End-to-end sanity check against the actual current resume file, so a
    future change to strip_latex or the resume template itself can't silently
    reintroduce this class of bug without a test failing."""

    def test_experience_section_is_not_gutted(self):
        from latex_parser import parse_resume

        resume_path = Path(__file__).parent.parent / "resume" / "main.tex"
        data = parse_resume(str(resume_path))
        experience_text = data["sections"].get("Experience", "")
        plain = strip_latex(experience_text)
        # Before the fix, the Experience section collapsed to just company
        # names/dates/locations — a few hundred characters. A resume with
        # real bullet content should be several thousand.
        assert len(plain) > 2000, (
            f"Experience section plain text is only {len(plain)} chars — "
            "bullets/techlines may be getting silently stripped again."
        )
