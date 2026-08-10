"""SQLite schema and connection management for the credentials module."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "credentials.db")

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id            TEXT PRIMARY KEY,
    resume_id     TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    site_url      TEXT,
    login_email   TEXT NOT NULL,
    username      TEXT,
    password_enc  TEXT NOT NULL,
    notes         TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credentials_resume ON credentials(resume_id);
"""


def get_conn() -> sqlite3.Connection:
    """Return this thread's SQLite connection, opening one on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create the credentials table if it doesn't already exist."""
    conn = get_conn()
    conn.executescript(SCHEMA)
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
