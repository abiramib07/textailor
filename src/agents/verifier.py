"""
Verifier Agent — re-checks the ATS scorer's keyword results two ways:

1. Exact match  : same substring search the scorer uses, but also captures
                  the actual line the keyword appears on (for traceability).
2. Semantic match: for keywords that failed the exact check, asks Claude
                  whether the resume demonstrates that skill/experience
                  without using the literal phrase — with justification.

This exists because the scorer's exact-substring check can produce false
positives/negatives that look identical to the user (both just "found" or
"missing") with no way to tell which kind of match actually happened.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_SEMANTIC_PROMPT = """You are verifying whether a resume demonstrates certain skills, even if the
exact keyword phrase is not literally present.

For EACH keyword below, decide if the resume's content semantically shows that skill or experience —
through related tools, described work, or synonyms — even without the literal phrase.

Output ONLY a raw JSON array (no markdown fences, no explanation outside JSON):
[
  {{"keyword": "...", "semantically_covered": true/false, "justification": "one sentence citing what in the resume supports this, or empty string if not covered"}}
]

KEYWORDS TO CHECK:
{keywords}

RESUME:
{resume}
"""


def _find_line(keyword: str, text: str) -> str:
    """Return the first line containing an exact (case-insensitive) match, trimmed."""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    for line in text.splitlines():
        if pattern.search(line):
            stripped = line.strip()
            return stripped[:200]
    return ""


def _exact_check(keywords: list, text: str) -> dict:
    """Returns {keyword: line_excerpt_or_None}"""
    result = {}
    for kw in keywords:
        line = _find_line(kw, text)
        result[kw] = line or None
    return result


def _semantic_check(keywords: list, resume_text: str) -> dict:
    """Batched single Claude call for every keyword that failed the exact check.
    Returns {keyword: {semantically_covered, justification}}"""
    if not keywords:
        return {}

    prompt = _SEMANTIC_PROMPT.format(
        keywords="\n".join(f"- {kw}" for kw in keywords),
        resume=resume_text.strip(),
    )
    raw = ask_claude(prompt)
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return {kw: {"semantically_covered": False, "justification": ""} for kw in keywords}

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return {kw: {"semantically_covered": False, "justification": ""} for kw in keywords}

    result = {}
    for item in parsed:
        kw = item.get("keyword", "")
        result[kw] = {
            "semantically_covered": bool(item.get("semantically_covered", False)),
            "justification": item.get("justification", ""),
        }
    # Fill in any keyword Claude skipped
    for kw in keywords:
        if kw not in result:
            result[kw] = {"semantically_covered": False, "justification": ""}
    return result


def verify(recruiter_result: dict, resume_plain_text: str) -> dict:
    """
    Returns:
    {
      "keywords": [
        {"keyword": str, "status": "exact" | "semantic" | "missing",
         "evidence": str, "required": bool}
      ]
    }
    """
    required = recruiter_result.get("required_keywords", [])
    preferred = recruiter_result.get("preferred_keywords", [])
    all_keywords = [(kw, True) for kw in required] + [(kw, False) for kw in preferred]

    exact_results = _exact_check([kw for kw, _ in all_keywords], resume_plain_text)
    needs_semantic = [kw for kw, line in exact_results.items() if not line]
    semantic_results = _semantic_check(needs_semantic, resume_plain_text)

    keywords_out = []
    for kw, is_required in all_keywords:
        line = exact_results.get(kw)
        if line:
            keywords_out.append(
                {"keyword": kw, "status": "exact", "evidence": line, "required": is_required}
            )
            continue

        sem = semantic_results.get(kw, {"semantically_covered": False, "justification": ""})
        if sem["semantically_covered"]:
            keywords_out.append(
                {
                    "keyword": kw,
                    "status": "semantic",
                    "evidence": sem["justification"],
                    "required": is_required,
                }
            )
        else:
            keywords_out.append(
                {"keyword": kw, "status": "missing", "evidence": "", "required": is_required}
            )

    return {"keywords": keywords_out}


def explain_keyword(keyword: str, resume_plain_text: str) -> dict:
    """Ad-hoc lookup for a single keyword not necessarily in the recruiter's list —
    powers the "where did you add X" chat-style query."""
    line = _find_line(keyword, resume_plain_text)
    if line:
        return {"keyword": keyword, "status": "exact", "evidence": line}

    sem = _semantic_check([keyword], resume_plain_text)
    result = sem.get(keyword, {"semantically_covered": False, "justification": ""})
    if result["semantically_covered"]:
        return {"keyword": keyword, "status": "semantic", "evidence": result["justification"]}
    return {"keyword": keyword, "status": "missing", "evidence": ""}
