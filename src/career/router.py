"""FastAPI routes for `/api/career/*`: personal info clipboard, apply-later
queue, job-post archive with screenshot attachments, interview prep
checklists, and JD topic mapping. Mounted into the main app by `src.api`.
"""

import logging
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agents.job_finder import stream_find_jobs
from latex_parser import extract_contact_fields, extract_skill_list, parse_resume
from resumes.db import get_resume, resolve_resume_id

from .db import ATTACHMENTS_DIR, get_conn, tx
from .email_link import add_checklist_topics
from .schemas import (
    ApplyLaterCreate,
    ApplyLaterSearch,
    ApplyLaterUpdate,
    InterviewTopicCreate,
    InterviewTopicUpdate,
    JobPostCreate,
    PersonalInfoUpsert,
    SeedSkillsRequest,
)

log = logging.getLogger("textailor.career")

router = APIRouter(prefix="/api/career", tags=["career"])

# Personal-info keys that can be auto-filled from the resume header when the
# user hasn't already saved their own value for them.
_RESUME_DERIVED_KEYS = {
    "full_name": "name",
    "email": "email",
    "phone": "phone",
    "linkedin_url": "linkedin",
    "github_url": "github",
}


def _resume_derived_defaults(resume_id: str) -> dict[str, str]:
    """Best-effort contact fields pulled straight from the resume header,
    keyed by personal-info field name. Returns {} if the resume can't be
    read for any reason — this is a convenience fallback, not required."""
    resume = get_resume(resume_id)
    if not resume:
        return {}
    try:
        data = parse_resume(resume["tex_path"])
        contact = extract_contact_fields(data["profile"])
    except Exception:
        log.exception("Could not derive contact defaults from resume %s (non-fatal)", resume_id)
        return {}
    return {
        field_key: contact[contact_key]
        for field_key, contact_key in _RESUME_DERIVED_KEYS.items()
        if contact.get(contact_key)
    }


def _resume_skills(resume_id: str) -> list[str]:
    """Flat list of individual skills/tools from the resume's Technical
    Skills section. Returns [] if the resume can't be read for any reason —
    this is a convenience feature, not required for these tools to work."""
    resume = get_resume(resume_id)
    if not resume:
        return []
    try:
        data = parse_resume(resume["tex_path"])
        return extract_skill_list(data["sections"])
    except Exception:
        log.exception("Could not extract skills from resume %s (non-fatal)", resume_id)
        return []


# task_id -> {"status": "running"|"done"|"error", "trace": [...], "entries": [...],
# "search_note": str, "error": str|None} — same in-memory background-task + polling
# pattern the core pipeline uses for /api/generate + /api/status.
_search_tasks: dict[str, dict] = {}

_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


# ── Personal info clipboard ──────────────────────────────────────────────────
@router.get("/personal-info")
def list_personal_info(resume_id: str) -> dict:
    """Return every personal-info field for one resume identity, e.g.
    linkedin_url, short_pitch. Contact fields (name, email, phone, LinkedIn,
    GitHub) the user hasn't explicitly saved yet are auto-filled from the
    resume header so the clipboard is never empty on first use."""
    resume_id = resolve_resume_id(resume_id)
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, value FROM personal_info WHERE resume_id = ? ORDER BY key", (resume_id,)
    ).fetchall()
    values = {row["key"]: row["value"] for row in rows}

    for key, default_value in _resume_derived_defaults(resume_id).items():
        if not values.get(key):
            values[key] = default_value

    return {"entries": [{"key": k, "value": v} for k, v in sorted(values.items())]}


@router.put("/personal-info")
def upsert_personal_info(req: PersonalInfoUpsert) -> dict:
    """Create or update one personal-info field for a resume identity."""
    key = req.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Field name is required")
    with tx() as conn:
        conn.execute(
            "INSERT INTO personal_info (resume_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(resume_id, key) DO UPDATE SET "
            "value = excluded.value, updated_at = excluded.updated_at",
            (req.resume_id, key, req.value, time.time()),
        )
    return {"key": key, "value": req.value}


@router.delete("/personal-info/{key}")
def delete_personal_info(key: str, resume_id: str) -> dict:
    """Remove a personal-info field for a resume identity."""
    with tx() as conn:
        conn.execute("DELETE FROM personal_info WHERE key = ? AND resume_id = ?", (key, resume_id))
    return {"ok": True}


@router.get("/resume-skills")
def get_resume_skills(resume_id: str) -> dict:
    """Flat list of individual skills/tools from the resume's Technical
    Skills section — used to seed interview-prep topics, mark covered
    keywords in the topic map, and as a quick reference in the tracker."""
    resume_id = resolve_resume_id(resume_id)
    return {"skills": _resume_skills(resume_id)}


# ── Apply-later queue ─────────────────────────────────────────────────────────
@router.post("/apply-later")
def create_apply_later(req: ApplyLaterCreate) -> dict:
    """Queue a job application to track, starting at status 'Not Applied'."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")
    entry_id = str(uuid.uuid4())
    with tx() as conn:
        conn.execute(
            "INSERT INTO apply_later (id, resume_id, url, company_name, notes, tier, "
            "role_title, status, applied, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Not Applied', 0, ?)",
            (
                entry_id,
                req.resume_id,
                req.url.strip(),
                req.company_name.strip(),
                req.notes.strip(),
                req.tier.strip(),
                req.role_title.strip(),
                time.time(),
            ),
        )
    return _get_apply_later(entry_id)


@router.get("/apply-later")
def list_apply_later(resume_id: str) -> dict:
    """List every tracked application for a resume identity, newest first —
    grouping/sorting by tier or status happens client-side."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM apply_later WHERE resume_id = ? ORDER BY created_at DESC",
        (resume_id,),
    ).fetchall()
    return {"entries": [dict(r) for r in rows]}


_APPLY_LATER_TEXT_FIELDS = (
    "notes",
    "tier",
    "role_title",
    "status",
    "referral",
    "date_applied",
    "next_follow_up",
    "interview_round",
    "salary_discussed",
)


def _insert_found_postings(resume_id: str, postings: list[dict]) -> list[dict]:
    """Insert each web-search result as a new 'Not Applied' tracker row,
    folding the agent's salary evidence into notes (no separate column for
    it — it's a one-off research note, not something the user edits like
    `salary_discussed`). Skips any posting missing a company or link."""
    inserted_ids = []
    with tx() as conn:
        for posting in postings:
            if not posting.get("company") or not posting.get("job_link"):
                continue
            note_parts = [p for p in (posting.get("notes", ""),) if p]
            if posting.get("salary_evidence"):
                note_parts.append(f"Salary: {posting['salary_evidence']}")
            entry_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO apply_later (id, resume_id, url, company_name, notes, tier, "
                "role_title, status, applied, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, "
                "'Not Applied', 0, ?)",
                (
                    entry_id,
                    resume_id,
                    posting["job_link"],
                    posting["company"],
                    " | ".join(note_parts),
                    posting.get("tier", ""),
                    posting.get("role_title", ""),
                    time.time(),
                ),
            )
            inserted_ids.append(entry_id)

    conn = get_conn()
    return [
        dict(conn.execute("SELECT * FROM apply_later WHERE id = ?", (i,)).fetchone())
        for i in inserted_ids
    ]


def _run_job_search(
    task_id: str,
    resume_id: str,
    query: str,
    years_experience: int,
    location: str,
    count: int,
    min_salary_lpa: int | None,
) -> None:
    """Background-thread target: streams the job_finder agent's live trace
    into `_search_tasks[task_id]`, then inserts whatever real postings it
    found once it finishes."""
    task = _search_tasks[task_id]
    try:
        for event in stream_find_jobs(query, years_experience, location, count, min_salary_lpa):
            if event["type"] == "trace":
                task["trace"].append(event["text"])
            elif event["type"] == "error":
                task["status"] = "error"
                task["error"] = event["text"]
                return
            elif event["type"] == "done":
                data = event["data"]
                task["entries"] = _insert_found_postings(resume_id, data["postings"])
                task["search_note"] = data.get("search_note", "")
                task["status"] = "done"
                return
    except Exception as exc:
        log.exception("Job search failed  task_id=%s", task_id)
        task["status"] = "error"
        task["error"] = str(exc)


@router.post("/apply-later/search")
def start_apply_later_search(req: ApplyLaterSearch) -> dict:
    """Start a web-search job hunt in the background — returns immediately
    with a task_id to poll via GET /apply-later/search/{task_id} for live
    trace lines and, once done, the newly inserted entries."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Search query is required")
    task_id = str(uuid.uuid4())
    _search_tasks[task_id] = {
        "status": "running",
        "trace": [],
        "entries": [],
        "search_note": "",
        "error": None,
    }
    t = threading.Thread(
        target=_run_job_search,
        args=(
            task_id,
            req.resume_id,
            req.query,
            req.years_experience,
            req.location,
            req.count,
            req.min_salary_lpa,
        ),
        daemon=True,
    )
    t.start()
    return {"task_id": task_id}


@router.get("/apply-later/search/{task_id}")
def get_apply_later_search(task_id: str) -> dict:
    """Poll a running job search: live trace lines, status, and — once
    status is 'done' — the newly inserted entries and the agent's caveat
    note."""
    task = _search_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Search task not found")
    return {
        "status": task["status"],
        "trace": task["trace"],
        "entries": task["entries"],
        "search_note": task["search_note"],
        "error": task["error"],
    }


@router.patch("/apply-later/{entry_id}")
def update_apply_later(entry_id: str, req: ApplyLaterUpdate) -> dict:
    """Update only the fields provided — applied flag, or any tracker field
    (tier, status, referral, dates, interview round, salary)."""
    conn = get_conn()
    existing = conn.execute("SELECT id FROM apply_later WHERE id = ?", (entry_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    with tx() as conn:
        if req.applied is not None:
            conn.execute(
                "UPDATE apply_later SET applied = ? WHERE id = ?", (int(req.applied), entry_id)
            )
        for field in _APPLY_LATER_TEXT_FIELDS:
            value = getattr(req, field)
            if value is not None:
                conn.execute(f"UPDATE apply_later SET {field} = ? WHERE id = ?", (value, entry_id))
    return _get_apply_later(entry_id)


@router.delete("/apply-later/{entry_id}")
def delete_apply_later(entry_id: str) -> dict:
    """Remove an entry from the apply-later queue."""
    with tx() as conn:
        conn.execute("DELETE FROM apply_later WHERE id = ?", (entry_id,))
    return {"ok": True}


def _get_apply_later(entry_id: str) -> dict:
    row = get_conn().execute("SELECT * FROM apply_later WHERE id = ?", (entry_id,)).fetchone()
    return {"entry": dict(row) if row else None}


# ── Job post / LinkedIn archive ───────────────────────────────────────────────
@router.post("/posts")
def create_job_post(req: JobPostCreate) -> dict:
    """Archive a job post — a URL, pasted text, or both (screenshots added separately)."""
    if not req.url.strip() and not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Provide a URL or pasted text")
    post_id = str(uuid.uuid4())
    with tx() as conn:
        conn.execute(
            "INSERT INTO job_posts (id, resume_id, url, company_name, role_title, raw_text, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                post_id,
                req.resume_id,
                req.url.strip(),
                req.company_name.strip(),
                req.role_title.strip(),
                req.raw_text.strip(),
                time.time(),
            ),
        )
    return _get_job_post(post_id)


@router.get("/posts")
def list_job_posts(resume_id: str) -> dict:
    """List every archived job post for a resume identity, newest first, with its attachment count."""
    conn = get_conn()
    posts = conn.execute(
        "SELECT * FROM job_posts WHERE resume_id = ? ORDER BY created_at DESC", (resume_id,)
    ).fetchall()
    result = []
    for p in posts:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM job_post_attachments WHERE job_post_id = ?", (p["id"],)
        ).fetchone()["n"]
        result.append({**dict(p), "attachment_count": count})
    return {"entries": result}


@router.delete("/posts/{post_id}")
def delete_job_post(post_id: str) -> dict:
    """Delete an archived job post and its attachment files."""
    conn = get_conn()
    attachments = conn.execute(
        "SELECT file_path FROM job_post_attachments WHERE job_post_id = ?", (post_id,)
    ).fetchall()
    for a in attachments:
        Path(a["file_path"]).unlink(missing_ok=True)
    with tx() as conn:
        conn.execute("DELETE FROM job_post_attachments WHERE job_post_id = ?", (post_id,))
        conn.execute("DELETE FROM job_posts WHERE id = ?", (post_id,))
    return {"ok": True}


def _get_job_post(post_id: str) -> dict:
    row = get_conn().execute("SELECT * FROM job_posts WHERE id = ?", (post_id,)).fetchone()
    return {"entry": dict(row) if row else None}


@router.post("/posts/{post_id}/attachments")
async def upload_attachment(post_id: str, file: UploadFile = File(...)) -> dict:
    """Attach a screenshot to an archived job post (paste-to-save from the clipboard)."""
    conn = get_conn()
    post = conn.execute("SELECT id FROM job_posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        raise HTTPException(status_code=404, detail="Job post not found")

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    data = await file.read()
    if len(data) > _MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="Screenshot too large (10 MB max)")

    post_dir = ATTACHMENTS_DIR / post_id
    post_dir.mkdir(parents=True, exist_ok=True)
    attachment_id = str(uuid.uuid4())
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}[
        file.content_type
    ]
    file_path = post_dir / f"{attachment_id}.{ext}"
    file_path.write_bytes(data)

    with tx() as conn:
        conn.execute(
            "INSERT INTO job_post_attachments (id, job_post_id, file_path, created_at) "
            "VALUES (?, ?, ?, ?)",
            (attachment_id, post_id, str(file_path), time.time()),
        )
    log.info("Attachment saved  post_id=%s  attachment_id=%s", post_id, attachment_id)
    return {"attachment_id": attachment_id}


@router.get("/posts/{post_id}/attachments")
def list_attachments(post_id: str) -> dict:
    """List every screenshot attached to a job post."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, created_at FROM job_post_attachments WHERE job_post_id = ? ORDER BY created_at",
        (post_id,),
    ).fetchall()
    return {"entries": [dict(r) for r in rows]}


@router.get("/posts/{post_id}/attachments/{attachment_id}")
def get_attachment(post_id: str, attachment_id: str) -> FileResponse:
    """Serve one screenshot image."""
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM job_post_attachments WHERE id = ? AND job_post_id = ?",
        (attachment_id, post_id),
    ).fetchone()
    if not row or not Path(row["file_path"]).exists():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(row["file_path"])


@router.delete("/posts/{post_id}/attachments/{attachment_id}")
def delete_attachment(post_id: str, attachment_id: str) -> dict:
    """Remove one screenshot attachment."""
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM job_post_attachments WHERE id = ? AND job_post_id = ?",
        (attachment_id, post_id),
    ).fetchone()
    if row:
        Path(row["file_path"]).unlink(missing_ok=True)
    with tx() as conn:
        conn.execute("DELETE FROM job_post_attachments WHERE id = ?", (attachment_id,))
    return {"ok": True}


# ── Interview prep checklist ──────────────────────────────────────────────────
@router.post("/interview-topics")
def create_interview_topic(req: InterviewTopicCreate) -> dict:
    """Add a topic to a company's interview prep checklist."""
    topic_id = str(uuid.uuid4())
    with tx() as conn:
        conn.execute(
            "INSERT INTO interview_topics "
            "(id, resume_id, company_name, topic, covered, github_url, youtube_url, notes, "
            "created_at) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (
                topic_id,
                req.resume_id,
                req.company_name.strip(),
                req.topic.strip(),
                req.github_url.strip(),
                req.youtube_url.strip(),
                req.notes.strip(),
                time.time(),
            ),
        )
    return _get_interview_topic(topic_id)


@router.post("/interview-topics/seed-skills")
def seed_interview_topics_from_skills(req: SeedSkillsRequest) -> dict:
    """Add every resume Technical Skill not already on this company's
    interview-prep checklist as a new, unchecked topic — a one-click way to
    prep on everything you claim to know, not just what one job post asked."""
    company = req.company_name.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required")
    resume_id = resolve_resume_id(req.resume_id)
    skills = _resume_skills(resume_id)
    if not skills:
        raise HTTPException(
            status_code=400, detail="No Technical Skills found in this resume to seed from"
        )
    added = add_checklist_topics(resume_id, company, skills)
    return {"added": added}


@router.get("/interview-topics")
def list_interview_topics(resume_id: str, company_name: str = "") -> dict:
    """List interview-prep topics for a resume identity, optionally filtered to one company."""
    conn = get_conn()
    if company_name:
        rows = conn.execute(
            "SELECT * FROM interview_topics WHERE resume_id = ? AND company_name = ? "
            "ORDER BY created_at",
            (resume_id, company_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM interview_topics WHERE resume_id = ? ORDER BY company_name, created_at",
            (resume_id,),
        ).fetchall()
    return {"entries": [dict(r) for r in rows]}


@router.get("/interview-topics/companies")
def list_interview_companies(resume_id: str) -> dict:
    """List every distinct company that has interview-prep topics for a resume identity."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT company_name FROM interview_topics WHERE resume_id = ? "
        "ORDER BY company_name",
        (resume_id,),
    ).fetchall()
    return {"companies": [r["company_name"] for r in rows]}


@router.patch("/interview-topics/{topic_id}")
def update_interview_topic(topic_id: str, req: InterviewTopicUpdate) -> dict:
    """Update a topic's covered state, links, or notes."""
    conn = get_conn()
    existing = conn.execute("SELECT id FROM interview_topics WHERE id = ?", (topic_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Topic not found")

    with tx() as conn:
        if req.covered is not None:
            conn.execute(
                "UPDATE interview_topics SET covered = ? WHERE id = ?",
                (int(req.covered), topic_id),
            )
        if req.github_url is not None:
            conn.execute(
                "UPDATE interview_topics SET github_url = ? WHERE id = ?",
                (req.github_url, topic_id),
            )
        if req.youtube_url is not None:
            conn.execute(
                "UPDATE interview_topics SET youtube_url = ? WHERE id = ?",
                (req.youtube_url, topic_id),
            )
        if req.notes is not None:
            conn.execute(
                "UPDATE interview_topics SET notes = ? WHERE id = ?", (req.notes, topic_id)
            )
    return _get_interview_topic(topic_id)


@router.delete("/interview-topics/{topic_id}")
def delete_interview_topic(topic_id: str) -> dict:
    """Remove a topic from the checklist."""
    with tx() as conn:
        conn.execute("DELETE FROM interview_topics WHERE id = ?", (topic_id,))
    return {"ok": True}


def _get_interview_topic(topic_id: str) -> dict:
    row = get_conn().execute("SELECT * FROM interview_topics WHERE id = ?", (topic_id,)).fetchone()
    return {"entry": dict(row) if row else None}


def _keyword_covered(keyword: str, skills: list[str]) -> bool:
    """True if a JD-observed keyword matches one of the resume's skills —
    exact match, or one appears as a whole word/phrase inside the other
    (case-insensitive), so e.g. keyword "RAG" matches resume skill
    "Retrieval-Augmented Generation (RAG)". Matching is anchored to word
    boundaries rather than raw substring so a short skill like "NER" can't
    false-positive match unrelated text that happens to contain the same
    letters mid-word (e.g. "ge-NER-ative")."""
    kw = keyword.strip().lower()
    if not kw:
        return False
    for skill in skills:
        s = skill.strip().lower()
        if not s:
            continue
        if kw == s:
            return True
        if re.search(rf"\b{re.escape(s)}\b", kw) or re.search(rf"\b{re.escape(kw)}\b", s):
            return True
    return False


# ── JD topic mapping ──────────────────────────────────────────────────────────
@router.get("/topic-map")
def get_topic_map(resume_id: str, years_bucket: str = "") -> dict:
    """Return keyword frequency across every JD analysed so far for a resume
    identity, most in-demand first — optionally filtered to one
    years-of-experience bucket. Each entry is flagged `covered` if it
    matches one of the resume's Technical Skills, turning the frequency
    chart into an at-a-glance skill-gap view."""
    resume_id = resolve_resume_id(resume_id)
    skills = _resume_skills(resume_id)
    conn = get_conn()
    if years_bucket:
        rows = conn.execute(
            "SELECT keyword, category, years_bucket, COUNT(*) AS frequency "
            "FROM jd_keyword_observations WHERE resume_id = ? AND years_bucket = ? "
            "GROUP BY keyword, category, years_bucket ORDER BY frequency DESC",
            (resume_id, years_bucket),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT keyword, category, years_bucket, COUNT(*) AS frequency "
            "FROM jd_keyword_observations WHERE resume_id = ? "
            "GROUP BY keyword, category, years_bucket ORDER BY frequency DESC",
            (resume_id,),
        ).fetchall()
    entries = [dict(r) for r in rows]
    for entry in entries:
        entry["covered"] = _keyword_covered(entry["keyword"], skills)
    return {"entries": entries}


@router.get("/topic-map/buckets")
def list_years_buckets(resume_id: str) -> dict:
    """List every distinct years-of-experience bucket seen so far for a resume identity."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT years_bucket FROM jd_keyword_observations "
        "WHERE resume_id = ? AND years_bucket IS NOT NULL ORDER BY years_bucket",
        (resume_id,),
    ).fetchall()
    return {"buckets": [r["years_bucket"] for r in rows]}
