"""Links a finalized application email to the career tracker: records the
sent email, creates or updates its Apply Later row, and feeds the job
post's keywords into the topic map and interview-prep checklist.
"""

import logging
import sqlite3
import time
import uuid

from agents.recruiter import analyze as analyze_jd

from .db import tx
from .topic_mapping import log_keywords

log = logging.getLogger("textailor.career.email_link")


def save_email_context(
    email_id: str,
    resume_id: str,
    company_name: str,
    role_title: str,
    to_addr: str,
    subject: str,
    body: str,
    source_url: str,
    job_post_text: str,
    resume_plain_text: str,
) -> dict:
    """Persist a finalized email, link/update its Apply Later row, and
    auto-populate the topic map and interview-prep checklist from the job
    post's keywords. Returns a summary for the UI confirmation banner.
    """
    now = time.time()
    company = company_name.strip()
    source_url = source_url.strip()

    with tx() as conn:
        apply_later_id, created = _link_apply_later(
            conn, resume_id, company, role_title.strip(), source_url, now
        )
        # Upsert, not insert — saving the same email_id twice (e.g. a double
        # click) should just refresh the record, not crash on the primary
        # key that a plain INSERT would collide with.
        conn.execute(
            "INSERT INTO sent_emails (id, resume_id, apply_later_id, company_name, role_title, "
            "to_addr, subject, body, source_url, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "resume_id = excluded.resume_id, apply_later_id = excluded.apply_later_id, "
            "company_name = excluded.company_name, role_title = excluded.role_title, "
            "to_addr = excluded.to_addr, subject = excluded.subject, body = excluded.body, "
            "source_url = excluded.source_url, sent_at = excluded.sent_at",
            (
                email_id,
                resume_id,
                apply_later_id,
                company,
                role_title.strip(),
                to_addr,
                subject,
                body,
                source_url,
                now,
            ),
        )

    topics_added: list[str] = []
    keywords_logged = 0
    if company and job_post_text.strip():
        try:
            recruiter_result = analyze_jd(job_post_text, resume_plain_text)
            keywords = [
                *recruiter_result.get("required_keywords", []),
                *recruiter_result.get("preferred_keywords", []),
            ]
            if keywords:
                log_keywords(None, recruiter_result, job_post_text, resume_id)
                keywords_logged = len(keywords)
                topics_added = add_checklist_topics(resume_id, company, keywords)
        except Exception:
            log.exception("Keyword extraction on email save failed (non-fatal)")

    return {
        "apply_later_id": apply_later_id,
        "apply_later_created": created,
        "topics_added": topics_added,
        "keywords_logged": keywords_logged,
    }


def _link_apply_later(
    conn: sqlite3.Connection,
    resume_id: str,
    company: str,
    role_title: str,
    source_url: str,
    now: float,
) -> tuple[str | None, bool]:
    """Mark the most recent Apply Later row for this company as Applied, or
    create a new one if none exists. Returns (apply_later_id, created) —
    id is None if no company name was given to match or create against."""
    if not company:
        return None, False

    row = conn.execute(
        "SELECT id, date_applied FROM apply_later WHERE resume_id = ? "
        "AND LOWER(company_name) = LOWER(?) ORDER BY created_at DESC LIMIT 1",
        (resume_id, company),
    ).fetchone()

    today = time.strftime("%Y-%m-%d", time.localtime(now))
    if row:
        date_applied = row["date_applied"] or today
        conn.execute(
            "UPDATE apply_later SET status = 'Applied', date_applied = ? WHERE id = ?",
            (date_applied, row["id"]),
        )
        return str(row["id"]), False

    entry_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO apply_later (id, resume_id, url, company_name, notes, tier, role_title, "
        "status, applied, date_applied, created_at) "
        "VALUES (?, ?, ?, ?, '', '', ?, 'Applied', 1, ?, ?)",
        (entry_id, resume_id, source_url, company, role_title, today, now),
    )
    return entry_id, True


def add_checklist_topics(resume_id: str, company: str, keywords: list[str]) -> list[str]:
    """Add every keyword not already on this company's interview-prep
    checklist as a new, unchecked topic. Returns the topics actually added.

    Shared by the JD-keyword auto-add path (email save) and the
    resume-skills "seed" action in `career/router.py`.
    """
    now = time.time()
    added: list[str] = []
    with tx() as conn:
        existing = {
            str(row["topic"]).lower()
            for row in conn.execute(
                "SELECT topic FROM interview_topics WHERE resume_id = ? AND company_name = ?",
                (resume_id, company),
            )
        }
        seen: set[str] = set()
        for keyword in keywords:
            topic = keyword.strip()
            key = topic.lower()
            if not topic or key in existing or key in seen:
                continue
            seen.add(key)
            conn.execute(
                "INSERT INTO interview_topics (id, resume_id, company_name, topic, covered, "
                "github_url, youtube_url, notes, created_at) "
                "VALUES (?, ?, ?, ?, 0, '', '', '', ?)",
                (str(uuid.uuid4()), resume_id, company, topic, now),
            )
            added.append(topic)
    return added
