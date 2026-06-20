import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_PROMPT = """You are an expert resume writer specialising in ATS-optimised LaTeX resumes.

Your task: rewrite the LaTeX content for the sections listed below.

RULES:
1. Rewrite bullet points using Google XYZ formula: "Accomplished [X], as measured by [Y], by doing [Z]"
2. Weave in the MISSING KEYWORDS naturally — do not stuff them; they must fit contextually
3. Mirror the JD's ACTION VERBS where possible (use them to start bullets)
4. Never invent metrics or experience — if a bullet has no measurable result, improve language only and mark it with %NEEDS_METRIC at the end of that line
5. Preserve ALL LaTeX commands exactly: \\item[], \\textbf{{}}, \\hfill, \\vspace{{}}, \\begin{{itemize}}, etc.
6. Only modify the human-readable text INSIDE \\item[] blocks and section prose
7. Do NOT touch the structure, spacing commands, or custom macros
8. Output each section wrapped in markers: ===BEGIN SECTION: Name=== and ===END SECTION: Name===
9. Output ONLY the rewritten LaTeX — no explanation, no markdown fences

MISSING KEYWORDS TO INCORPORATE (only if contextually honest):
{keywords}

JD ACTION VERBS TO USE:
{verbs}

SECTIONS TO REWRITE:
{sections}
"""

_SECTION_BLOCK = "===SECTION: {name}===\n{content}\n===END==="


def _build_section_input(sections: dict, names_to_rewrite: list) -> str:
    blocks = []
    for name in names_to_rewrite:
        if name in sections:
            blocks.append(_SECTION_BLOCK.format(name=name, content=sections[name]))
    return "\n\n".join(blocks)


def _parse_output(raw: str) -> dict:
    """Extract rewritten sections from Claude's marked output."""
    pattern = r"===BEGIN SECTION:\s*(.+?)===(.*?)===END SECTION:\s*\1==="
    matches = re.findall(pattern, raw, re.DOTALL)
    if matches:
        return {name.strip(): content.strip() for name, content in matches}

    # Fallback: try simpler markers
    pattern2 = r"===SECTION:\s*(.+?)===(.*?)===END==="
    matches2 = re.findall(pattern2, raw, re.DOTALL)
    return {name.strip(): content.strip() for name, content in matches2}


def rewrite(
    sections: dict,
    priority_keywords: list,
    key_action_verbs: list,
    sections_to_rewrite: list = None,
) -> dict:
    """
    Rewrite resume sections with JD keywords injected using Google XYZ formula.

    Args:
        sections           : dict from latex_parser.extract_sections()
        priority_keywords  : list from recruiter.analyze()["priority_adds"]
        key_action_verbs   : list from recruiter.analyze()["key_action_verbs"]
        sections_to_rewrite: subset of section names to rewrite (defaults to all except Education)

    Returns:
        dict of {section_name: rewritten_latex}
    """
    if sections_to_rewrite is None:
        sections_to_rewrite = [k for k in sections if k != "Education"]

    section_input = _build_section_input(sections, sections_to_rewrite)

    prompt = _PROMPT.format(
        keywords="\n".join(f"- {kw}" for kw in priority_keywords),
        verbs=", ".join(key_action_verbs),
        sections=section_input,
    )

    raw = ask_claude(prompt)
    return _parse_output(raw)


if __name__ == "__main__":
    import json
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from latex_parser import parse_resume
    from agents.recruiter import analyze

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
        print(f"\n{'='*60}")
        print(f"SECTION: {name}")
        print("=" * 60)
        print(content[:800])
