"""Auto-captures JD keyword observations for the topic-mapping tab.

Hooked into the main resume pipeline's recruiter step — every time a JD is
analysed, its required/preferred keywords are logged here with a rough
years-of-experience bucket parsed from the JD text, so the topic-mapping
tab can show "what are companies asking for" trends without any manual
data entry.
"""

import re
import time
import uuid

from .db import tx

_YEARS_RE = re.compile(r"(\d+)\s*\+?\s*(?:-|to)?\s*(\d+)?\+?\s*years?", re.IGNORECASE)


def parse_years_bucket(jd_text: str) -> str:
    """Heuristically bucket a JD's stated experience requirement."""
    match = _YEARS_RE.search(jd_text)
    if not match:
        return "unspecified"
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else low
    avg = (low + high) / 2
    if avg <= 2:
        return "0-2"
    if avg <= 5:
        return "3-5"
    return "5+"


def log_keywords(
    job_post_id: str | None, recruiter_result: dict, jd_text: str, resume_id: str
) -> None:
    """Record every required/preferred keyword from one JD analysis for a resume identity."""
    years_bucket = parse_years_bucket(jd_text)
    now = time.time()
    rows = [
        (str(uuid.uuid4()), resume_id, job_post_id, kw, "required", years_bucket, now)
        for kw in recruiter_result.get("required_keywords", [])
    ] + [
        (str(uuid.uuid4()), resume_id, job_post_id, kw, "preferred", years_bucket, now)
        for kw in recruiter_result.get("preferred_keywords", [])
    ]
    if not rows:
        return
    with tx() as conn:
        conn.executemany(
            "INSERT INTO jd_keyword_observations "
            "(id, resume_id, job_post_id, keyword, category, years_bucket, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
