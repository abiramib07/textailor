"""FastAPI routes for `/api/career/*`: personal info clipboard, apply-later
queue, job-post archive with screenshot attachments, interview prep
checklists, and JD topic mapping. Mounted into the main app by `src.api`.
"""

import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .db import ATTACHMENTS_DIR, get_conn, tx
from .schemas import (
    ApplyLaterCreate,
    ApplyLaterUpdate,
    InterviewTopicCreate,
    InterviewTopicUpdate,
    JobPostCreate,
    PersonalInfoUpsert,
)

log = logging.getLogger("textailor.career")

router = APIRouter(prefix="/api/career", tags=["career"])

_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


# ── Personal info clipboard ──────────────────────────────────────────────────
@router.get("/personal-info")
def list_personal_info(resume_id: str) -> dict:
    """Return every saved personal-info field for one resume identity, e.g.
    linkedin_url, short_pitch."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, value FROM personal_info WHERE resume_id = ? ORDER BY key", (resume_id,)
    ).fetchall()
    return {"entries": [dict(r) for r in rows]}


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


# ── Apply-later queue ─────────────────────────────────────────────────────────
@router.post("/apply-later")
def create_apply_later(req: ApplyLaterCreate) -> dict:
    """Queue a job application to finish later."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")
    entry_id = str(uuid.uuid4())
    with tx() as conn:
        conn.execute(
            "INSERT INTO apply_later (id, resume_id, url, company_name, notes, applied, "
            "created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                entry_id,
                req.resume_id,
                req.url.strip(),
                req.company_name.strip(),
                req.notes.strip(),
                time.time(),
            ),
        )
    return _get_apply_later(entry_id)


@router.get("/apply-later")
def list_apply_later(resume_id: str) -> dict:
    """List every queued application for a resume identity, unapplied first, then newest first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM apply_later WHERE resume_id = ? ORDER BY applied ASC, created_at DESC",
        (resume_id,),
    ).fetchall()
    return {"entries": [dict(r) for r in rows]}


@router.patch("/apply-later/{entry_id}")
def update_apply_later(entry_id: str, req: ApplyLaterUpdate) -> dict:
    """Mark an application as applied and/or update its notes."""
    conn = get_conn()
    existing = conn.execute("SELECT id FROM apply_later WHERE id = ?", (entry_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    with tx() as conn:
        if req.applied is not None:
            conn.execute(
                "UPDATE apply_later SET applied = ? WHERE id = ?", (int(req.applied), entry_id)
            )
        if req.notes is not None:
            conn.execute("UPDATE apply_later SET notes = ? WHERE id = ?", (req.notes, entry_id))
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


# ── JD topic mapping ──────────────────────────────────────────────────────────
@router.get("/topic-map")
def get_topic_map(resume_id: str, years_bucket: str = "") -> dict:
    """Return keyword frequency across every JD analysed so far for a resume
    identity, most in-demand first — optionally filtered to one
    years-of-experience bucket."""
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
    return {"entries": [dict(r) for r in rows]}


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
