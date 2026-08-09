"""Regression tests for a critical rewriter.py bug reported by the user:

The rewrite prompt (rule 10) tells Claude to output ONLY valid LaTeX with
zero commentary. But rule 4 ("never invent metrics or experience") and the
"only if contextually honest" instruction on missing keywords create a real
conflict when the JD's missing keywords describe a domain (e.g. healthcare:
ICD/CPT/SNOMED, EHR, HL7/FHIR, HIPAA) entirely absent from the candidate's
actual background. When Claude correctly declines to fabricate that
experience, it sometimes expresses the refusal as prose ("I want to flag
something before doing this rewrite...") instead of complying with rule 10
— and nothing in the pipeline validated that the response was actually
LaTeX before splicing it into the .tex file:

  `_rewrite_section()` -> `_strip_leaked_commentary()` (only catches
  markdown-table-style trailing notes, not conversational refusals) ->
  `latex_patcher.patch()` (unguarded regex splice, no content validation)
  -> `compile_tex()` (LaTeX tolerates plain prose, so it compiles
  successfully) -> a PDF with AI commentary embedded in place of the
  Professional Summary / Technical Skills content, indistinguishable from
  a successful run unless read carefully.

These tests reproduce the exact failure mode with the real-world refusal
text, confirm the fix rejects it (falls back to the original section,
never silently corrupting resume content), and confirm a legitimate
rewrite still passes through unaffected.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import rewriter  # noqa: E402

# The actual leaked text from the bug report — a healthcare-keyword refusal
# for a candidate whose real background is enterprise brokerage/fintech AI.
_LEAKED_PROFESSIONAL_SUMMARY_RESPONSE = """PROFESSIONAL SUMMARY
I want to flag something before doing this rewrite. The "missing keywords" list includes healthcare-specific
claims — Medical coding standards (ICD/CPT/SNOMED), EHR systems/clinical document processing,
HL7/FHIR APIs, HIPAA compliance — but the actual professional summary describes a Generative AI
Developer working with enterprise brokerage clients (UBS, Morgan Stanley, Jio, Fyers, JPMorgan),
with no healthcare/clinical domain mentioned anywhere.
Can you confirm: does this candidate actually have healthcare/clinical-domain experience (EHR, HL7/FHIR,
HIPAA, medical coding) that just isn't shown in this excerpt?"""

_LEAKED_TECHNICAL_SKILLS_RESPONSE = """TECHNICAL SKILLS
I can help rewrite this Technical Skills section, but I want to flag something before I do: several of the
"missing keywords" are healthcare-domain skills — Medical coding standards (ICD, CPT, SNOMED),
EHR systems, HL7/FHIR APIs, HIPAA compliance. Nothing in the original resume content suggests
this candidate has any healthcare/clinical background.
Want me to proceed with the rewrite using the honest subset, or do you want to confirm the healthcare
background first?"""

_ORIGINAL_SUMMARY = (
    r"\fontsize{11}{12}\selectfont"
    "Generative AI Developer with 2.5+ years building production multi-agent LLM systems "
    "for enterprise brokerage clients (UBS, Morgan Stanley, Jio, Fyers, JPMorgan)."
)

_ORIGINAL_SKILLS = (
    r"\renewcommand{\arraystretch}{1.1}"
    r"\noindent\begin{tabularx}{\textwidth}{@{}p{5.6cm} X@{}}"
    r"\skillrow{Languages}{Python}"
    r"\skillrow{Generative AI / NLP}{LLMs, RAG, Prompt Engineering}"
    r"\end{tabularx}"
)

_VALID_REWRITTEN_SUMMARY = (
    r"\fontsize{11}{12}\selectfont"
    "Generative AI Developer with 2.5+ years building production multi-agent LLM systems "
    "for enterprise brokerage clients (UBS, Morgan Stanley, Jio, Fyers, JPMorgan), skilled in "
    "AWS, GCP, and MLOps/CI/CD pipelines."
)


class TestRejectsLeakedConversationalResponse:
    """A response that's prose commentary instead of LaTeX content must
    never be used as the rewritten section — it must fall back to the
    original, unmodified content."""

    def test_professional_summary_refusal_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(
            rewriter, "ask_claude", lambda prompt: _LEAKED_PROFESSIONAL_SUMMARY_RESPONSE
        )
        result = rewriter.rewrite(
            sections={"Professional Summary": _ORIGINAL_SUMMARY},
            priority_keywords=["HIPAA compliance", "HL7/FHIR APIs"],
            key_action_verbs=["Built"],
            sections_to_rewrite=["Professional Summary"],
        )
        content = result[0] if isinstance(result, tuple) else result
        assert content["Professional Summary"] == _ORIGINAL_SUMMARY
        assert "I want to flag" not in content["Professional Summary"]
        assert "Can you confirm" not in content["Professional Summary"]

    def test_technical_skills_refusal_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(
            rewriter, "ask_claude", lambda prompt: _LEAKED_TECHNICAL_SKILLS_RESPONSE
        )
        result = rewriter.rewrite(
            sections={"Technical Skills": _ORIGINAL_SKILLS},
            priority_keywords=["Medical coding standards (ICD, CPT, SNOMED)"],
            key_action_verbs=[],
            sections_to_rewrite=["Technical Skills"],
        )
        content = result[0] if isinstance(result, tuple) else result
        assert content["Technical Skills"] == _ORIGINAL_SKILLS
        assert r"\skillrow" in content["Technical Skills"]
        assert "healthcare-domain skills" not in content["Technical Skills"]

    def test_rejection_is_surfaced_as_a_warning_not_silently_swallowed(self, monkeypatch) -> None:
        """The whole point of this fix is that the user must be told a
        section was kept unchanged, not just have it happen invisibly."""
        monkeypatch.setattr(
            rewriter, "ask_claude", lambda prompt: _LEAKED_PROFESSIONAL_SUMMARY_RESPONSE
        )
        result = rewriter.rewrite(
            sections={"Professional Summary": _ORIGINAL_SUMMARY},
            priority_keywords=["HIPAA compliance"],
            key_action_verbs=[],
            sections_to_rewrite=["Professional Summary"],
        )
        assert isinstance(result, tuple), (
            "rewrite() must return (content, warnings) so callers can surface the warning "
            "to the end user instead of it disappearing"
        )
        _, warnings = result
        assert len(warnings) == 1
        assert "Professional Summary" in warnings[0]


class TestLegitimateRewritesStillPassThrough:
    """The validator must not false-positive on normal, honest rewrites."""

    def test_valid_rewritten_summary_is_used_as_is(self, monkeypatch) -> None:
        monkeypatch.setattr(rewriter, "ask_claude", lambda prompt: _VALID_REWRITTEN_SUMMARY)
        result = rewriter.rewrite(
            sections={"Professional Summary": _ORIGINAL_SUMMARY},
            priority_keywords=["AWS", "GCP", "MLOps/CI/CD"],
            key_action_verbs=["Built"],
            sections_to_rewrite=["Professional Summary"],
        )
        content, warnings = result
        assert content["Professional Summary"] == _VALID_REWRITTEN_SUMMARY
        assert warnings == []

    def test_trailing_markdown_notes_are_still_stripped_not_rejected_outright(
        self, monkeypatch
    ) -> None:
        """Pre-existing behavior (_strip_leaked_commentary) for a *mostly*
        valid response with trailing markdown commentary must still work —
        this is a different, milder failure mode than a full conversational
        refusal, and shouldn't be downgraded to a full-section fallback."""
        response = _VALID_REWRITTEN_SUMMARY + "\n\n**Notes on keyword placement**\n- Added AWS naturally"
        monkeypatch.setattr(rewriter, "ask_claude", lambda prompt: response)
        result = rewriter.rewrite(
            sections={"Professional Summary": _ORIGINAL_SUMMARY},
            priority_keywords=["AWS"],
            key_action_verbs=[],
            sections_to_rewrite=["Professional Summary"],
        )
        content, warnings = result
        assert content["Professional Summary"] == _VALID_REWRITTEN_SUMMARY
        assert "Notes on keyword placement" not in content["Professional Summary"]
        assert warnings == []
