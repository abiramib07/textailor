"""SQLite schema and connection management for the career module."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "career.db")

ATTACHMENTS_DIR = _DATA_DIR / "attachments"
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

_local = threading.local()

SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS job_posts (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT,
    url           TEXT,
    company_name  TEXT,
    role_title    TEXT,
    raw_text      TEXT,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS job_post_attachments (
    id            TEXT PRIMARY KEY,
    job_post_id   TEXT NOT NULL REFERENCES job_posts(id),
    file_path     TEXT NOT NULL,
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_post ON job_post_attachments(job_post_id);

CREATE TABLE IF NOT EXISTS personal_info (
    resume_id     TEXT NOT NULL,
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    updated_at    REAL NOT NULL,
    PRIMARY KEY (resume_id, key)
);

CREATE TABLE IF NOT EXISTS apply_later (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT,
    url           TEXT NOT NULL,
    company_name  TEXT,
    notes         TEXT,
    applied       INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_topics (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT,
    company_name  TEXT NOT NULL,
    topic         TEXT NOT NULL,
    covered       INTEGER NOT NULL DEFAULT 0,
    github_url    TEXT,
    youtube_url   TEXT,
    notes         TEXT,
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interview_company ON interview_topics(company_name);

CREATE TABLE IF NOT EXISTS jd_keyword_observations (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT,
    job_post_id   TEXT,
    keyword       TEXT NOT NULL,
    category      TEXT,
    years_bucket  TEXT,
    observed_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_keyword_lookup ON jd_keyword_observations(keyword, years_bucket);

CREATE TABLE IF NOT EXISTS sent_emails (
    id              TEXT PRIMARY KEY,
    resume_id       TEXT,
    apply_later_id  TEXT,
    company_name    TEXT,
    role_title      TEXT,
    to_addr         TEXT,
    subject         TEXT,
    body            TEXT,
    source_url      TEXT,
    sent_at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sent_emails_company ON sent_emails(company_name);
"""

# Indexed after `_migrate` so `resume_id` is guaranteed to exist even on a
# database created before multi-resume support.
SCHEMA_RESUME_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_job_posts_resume ON job_posts(resume_id);
CREATE INDEX IF NOT EXISTS idx_apply_later_resume ON apply_later(resume_id);
CREATE INDEX IF NOT EXISTS idx_interview_resume ON interview_topics(resume_id);
CREATE INDEX IF NOT EXISTS idx_keyword_resume ON jd_keyword_observations(resume_id);
CREATE INDEX IF NOT EXISTS idx_sent_emails_resume ON sent_emails(resume_id);
"""


def get_conn() -> sqlite3.Connection:
    """Return this thread's SQLite connection, opening one on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str) -> None:
    """Add a nullable TEXT column to `table` if it doesn't already have one."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


def _migrate_personal_info(conn: sqlite3.Connection, default_resume_id: str) -> None:
    """Rebuild `personal_info` with a (resume_id, key) composite key — the
    original schema had `key` alone as the primary key, which would collide
    across two different resume identities using the same field name."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(personal_info)")}
    if "resume_id" in cols:
        return
    conn.execute("ALTER TABLE personal_info RENAME TO personal_info_old")
    conn.execute(
        "CREATE TABLE personal_info ("
        "resume_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "updated_at REAL NOT NULL, PRIMARY KEY (resume_id, key))"
    )
    conn.execute(
        "INSERT INTO personal_info (resume_id, key, value, updated_at) "
        "SELECT ?, key, value, updated_at FROM personal_info_old",
        (default_resume_id,),
    )
    conn.execute("DROP TABLE personal_info_old")


_APPLY_LATER_TRACKER_COLUMNS = (
    "tier",
    "role_title",
    "status",
    "referral",
    "date_applied",
    "next_follow_up",
    "interview_round",
    "salary_discussed",
)


def _migrate_apply_later_tracker_columns(conn: sqlite3.Connection) -> None:
    """Add the application-tracker fields to `apply_later` (tier, status
    pipeline, referral, dates, interview round, salary) for rows saved
    before this upgrade — `status` defaults to 'Not Applied' so existing
    entries render sensibly instead of showing blank."""
    for column in _APPLY_LATER_TRACKER_COLUMNS:
        _add_column_if_missing(conn, "apply_later", column)
    conn.execute("UPDATE apply_later SET status = 'Not Applied' WHERE status IS NULL")


def _migrate(conn: sqlite3.Connection, default_resume_id: str) -> None:
    """Backfill `resume_id` on rows saved before multi-resume support existed."""
    for table in ("job_posts", "apply_later", "interview_topics", "jd_keyword_observations"):
        _add_column_if_missing(conn, table, "resume_id")
        conn.execute(
            f"UPDATE {table} SET resume_id = ? WHERE resume_id IS NULL", (default_resume_id,)
        )
    _migrate_personal_info(conn, default_resume_id)
    _migrate_apply_later_tracker_columns(conn)
    conn.commit()


def init_db(default_resume_id: str) -> None:
    """Create the career tables if they don't already exist, backfill old
    rows to `default_resume_id`, then create the resume_id indexes."""
    conn = get_conn()
    conn.executescript(SCHEMA_TABLES)
    conn.commit()
    _migrate(conn, default_resume_id)
    conn.executescript(SCHEMA_RESUME_INDEXES)
    conn.commit()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and rolls back on exception."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
