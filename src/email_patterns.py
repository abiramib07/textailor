"""Persists email revision instructions as learned style patterns, scoped
per resume identity.

Every time the user revises a generated email ("make it shorter", "more
formal tone", ...), that instruction is recorded here. Future email
generations for the same resume identity pull the most recent patterns
back in automatically, so the same preference doesn't have to be typed in
again on every run.
"""

import sqlite3
import time
import uuid
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "auth" / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "email_patterns.db")

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS email_patterns (
    id          TEXT PRIMARY KEY,
    resume_id   TEXT,
    instruction TEXT NOT NULL,
    created_at  REAL NOT NULL
);
"""

# Indexed after `_migrate` so `resume_id` is guaranteed to exist even on a
# database created before multi-resume support.
SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_email_patterns_created ON email_patterns(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_patterns_resume ON email_patterns(resume_id);
"""


def _conn() -> sqlite3.Connection:
    """Open a fresh connection to email_patterns.db."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection, default_resume_id: str) -> None:
    """Backfill `resume_id` on rows recorded before multi-resume support existed."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(email_patterns)")}
    if "resume_id" not in cols:
        conn.execute("ALTER TABLE email_patterns ADD COLUMN resume_id TEXT")
    conn.execute(
        "UPDATE email_patterns SET resume_id = ? WHERE resume_id IS NULL", (default_resume_id,)
    )
    conn.commit()


def init_db(default_resume_id: str) -> None:
    """Create the email_patterns table if needed, backfill old rows to
    `default_resume_id`, then create indexes."""
    conn = _conn()
    conn.executescript(SCHEMA_TABLE)
    conn.commit()
    _migrate(conn, default_resume_id)
    conn.executescript(SCHEMA_INDEXES)
    conn.commit()
    conn.close()


def learn(instruction: str, resume_id: str) -> None:
    """Record a revision instruction as a learned style pattern for one resume identity."""
    instruction = instruction.strip()
    if not instruction:
        return
    conn = _conn()
    conn.execute(
        "INSERT INTO email_patterns (id, resume_id, instruction, created_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), resume_id, instruction, time.time()),
    )
    conn.commit()
    conn.close()


def recent_patterns(resume_id: str, limit: int = 15) -> list[str]:
    """Return the most recently learned instructions for one resume identity, newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT instruction FROM email_patterns WHERE resume_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (resume_id, limit),
    ).fetchall()
    conn.close()
    return [r["instruction"] for r in rows]
