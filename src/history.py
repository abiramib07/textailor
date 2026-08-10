"""SQLite-backed resume history: saved tailored resumes with company/role
metadata, scoped per resume identity and listed latest-first for the
History sidebar.
"""

import sqlite3
import time
import uuid
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "auth" / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "history.db")

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS resume_history (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT,
    company_name  TEXT NOT NULL,
    job_title     TEXT,
    job_url       TEXT,
    jd_text       TEXT,
    pdf_path      TEXT NOT NULL,
    ats_score     REAL,
    verdict       TEXT,
    applied_date  TEXT,
    created_at    REAL NOT NULL,
    resume_snapshot TEXT
);
"""

# Indexed after `_migrate` so `resume_id` is guaranteed to exist even on a
# database created before multi-resume support.
SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_history_created ON resume_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_resume ON resume_history(resume_id);
"""


def _conn() -> sqlite3.Connection:
    """Open a fresh connection (this module is called rarely enough that
    per-call connections are simpler than the thread-local pool in auth.db)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection, default_resume_id: str) -> None:
    """Backfill `resume_id` on rows saved before multi-resume support existed,
    add `jd_text` for rows saved before the Generator tab's Save action
    started persisting the job description alongside the entry, and add
    `resume_snapshot` for rows saved before entries started capturing the
    tailored resume's plain text (old rows keep it NULL — the original
    tex isn't recoverable after the fact)."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(resume_history)")}
    if "resume_id" not in cols:
        conn.execute("ALTER TABLE resume_history ADD COLUMN resume_id TEXT")
    if "jd_text" not in cols:
        conn.execute("ALTER TABLE resume_history ADD COLUMN jd_text TEXT")
    if "resume_snapshot" not in cols:
        conn.execute("ALTER TABLE resume_history ADD COLUMN resume_snapshot TEXT")
    conn.execute(
        "UPDATE resume_history SET resume_id = ? WHERE resume_id IS NULL", (default_resume_id,)
    )
    conn.commit()


def init_db(default_resume_id: str) -> None:
    """Create the resume_history table if needed, backfill old rows to
    `default_resume_id`, then create indexes."""
    conn = _conn()
    conn.executescript(SCHEMA_TABLE)
    conn.commit()
    _migrate(conn, default_resume_id)
    conn.executescript(SCHEMA_INDEXES)
    conn.commit()
    conn.close()


def save_entry(
    resume_id: str,
    company_name: str,
    job_title: str,
    job_url: str,
    jd_text: str,
    pdf_path: str,
    ats_score: float,
    verdict: str,
    applied_date: str,
    resume_snapshot: str | None = None,
) -> dict:
    """Insert a history entry and return it as saved."""
    entry_id = str(uuid.uuid4())
    conn = _conn()
    conn.execute(
        "INSERT INTO resume_history (id, resume_id, company_name, job_title, job_url, "
        "jd_text, pdf_path, ats_score, verdict, applied_date, created_at, resume_snapshot) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            resume_id,
            company_name,
            job_title,
            job_url,
            jd_text,
            pdf_path,
            ats_score,
            verdict,
            applied_date,
            time.time(),
            resume_snapshot,
        ),
    )
    conn.commit()
    conn.close()
    entry = get_entry(entry_id)
    assert entry is not None, "just-inserted history entry must exist"
    return entry


def list_entries(resume_id: str) -> list:
    """Return every saved history entry for one resume identity, newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM resume_history WHERE resume_id = ? ORDER BY created_at DESC", (resume_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entry(entry_id: str) -> dict | None:
    """Look up one history entry by id, or None if it doesn't exist."""
    conn = _conn()
    row = conn.execute("SELECT * FROM resume_history WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
