"""ATS scorer — computes a keyword-match score for the tailored resume
against the recruiter's gap analysis and writes a plain-text report.
"""

import re
import sys
from datetime import datetime


def _keyword_present(keyword: str, text: str) -> bool:
    """Case-insensitive substring check for one keyword in the resume text."""
    return bool(re.search(re.escape(keyword), text, re.IGNORECASE))


def score(recruiter_result: dict, rewritten_plain_text: str) -> dict:
    """
    Compute ATS match score against the recruiter keyword analysis.

    Args:
        recruiter_result    : dict from recruiter.analyze()
        rewritten_plain_text: plain text of the tailored resume

    Returns:
        dict with score, breakdown, and report lines
    """
    required = recruiter_result.get("required_keywords", [])
    preferred = recruiter_result.get("preferred_keywords", [])

    req_found = [kw for kw in required if _keyword_present(kw, rewritten_plain_text)]
    req_missing = [kw for kw in required if kw not in req_found]
    pref_found = [kw for kw in preferred if _keyword_present(kw, rewritten_plain_text)]
    pref_missing = [kw for kw in preferred if kw not in pref_found]

    req_score = (len(req_found) / len(required) * 100) if required else 100
    pref_score = (len(pref_found) / len(preferred) * 100) if preferred else 100
    # Weight: required 80%, preferred 20%
    overall = round(req_score * 0.8 + pref_score * 0.2, 1)

    needs_metric = rewritten_plain_text.count("%NEEDS_METRIC")

    return {
        "overall_score": overall,
        "required_score": round(req_score, 1),
        "preferred_score": round(pref_score, 1),
        "required_found": req_found,
        "required_missing": req_missing,
        "preferred_found": pref_found,
        "preferred_missing": pref_missing,
        "needs_metric_count": needs_metric,
        "job_title": recruiter_result.get("job_title", ""),
        "verdict": "Ready to submit" if overall >= 85 else "Review gaps before submitting",
    }


def write_report(score_result: dict, output_path: str) -> None:
    """Write the ATS score breakdown to a plain-text report file and echo it
    to the console (degrading gracefully on non-UTF-8 console codepages)."""
    lines = [
        f"TexTailor ATS Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Role: {score_result['job_title']}",
        "=" * 60,
        f"Overall ATS Match  : {score_result['overall_score']}%",
        f"Required keywords  : {score_result['required_score']}%  "
        f"({len(score_result['required_found'])}/{len(score_result['required_found']) + len(score_result['required_missing'])} found)",
        f"Preferred keywords : {score_result['preferred_score']}%  "
        f"({len(score_result['preferred_found'])}/{len(score_result['preferred_found']) + len(score_result['preferred_missing'])} found)",
        f"Verdict            : {score_result['verdict']}",
        "",
        "--- REQUIRED KEYWORDS MISSING ---",
    ]
    if score_result["required_missing"]:
        lines += [f"  ✗ {kw}" for kw in score_result["required_missing"]]
    else:
        lines.append("  All required keywords covered!")

    lines += ["", "--- PREFERRED KEYWORDS MISSING ---"]
    if score_result["preferred_missing"]:
        lines += [f"  ✗ {kw}" for kw in score_result["preferred_missing"]]
    else:
        lines.append("  All preferred keywords covered!")

    if score_result["needs_metric_count"] > 0:
        lines += [
            "",
            f"--- ACTION NEEDED: {score_result['needs_metric_count']} bullet(s) flagged with %NEEDS_METRIC ---",
            "  Search for %NEEDS_METRIC in resume_tailored.tex and add real numbers.",
        ]

    report_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    try:
        print(report_text)
    except UnicodeEncodeError:
        # Windows console codepages (e.g. cp1252) can't encode ✓/✗ — the file
        # write above already has the real UTF-8 content, so just degrade
        # the console echo instead of crashing the pipeline over a print().
        print(
            report_text.encode(sys.stdout.encoding or "ascii", errors="replace").decode(
                sys.stdout.encoding or "ascii"
            )
        )
