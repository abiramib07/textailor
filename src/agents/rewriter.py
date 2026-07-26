"""Rewriter agent — tailors each resume section's LaTeX content to a job
description's missing keywords and action verbs, one Claude call per section.
"""

import logging
import re
import sys
import time
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


def _rewrite_section(name: str, content: str, keywords: list, verbs: list) -> str:
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
    return result


def rewrite(
    sections: dict,
    priority_keywords: list,
    key_action_verbs: list,
    sections_to_rewrite: list | None = None,
) -> dict:
    """Call Claude once per section to avoid timeout on large prompts."""
    if sections_to_rewrite is None:
        sections_to_rewrite = [k for k in sections if k != "Education"]

    result = {}
    for name in sections_to_rewrite:
        if name not in sections:
            continue
        log.info("rewriting section: %s (%d keywords to weave in)", name, len(priority_keywords))
        try:
            result[name] = _rewrite_section(
                name, sections[name], priority_keywords, key_action_verbs
            )
            log.info("done: %s", name)
        except Exception:
            log.exception("%s failed — keeping original section unchanged", name)
            result[name] = sections[name]
    return result


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
    result = rewrite(
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
