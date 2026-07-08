import sqlite3
import threading
from contextlib import contextmanager

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    mobile_number   TEXT UNIQUE,
    mobile_verified INTEGER NOT NULL DEFAULT 0,
    pin_hash        TEXT,
    google_sub      TEXT UNIQUE,
    failed_pin_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    REAL,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS otp_requests (
    id              TEXT PRIMARY KEY,
    mobile_number   TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    otp_hash        TEXT NOT NULL,
    expires_at      REAL NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    consumed        INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_otp_mobile_purpose ON otp_requests(mobile_number, purpose);

CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    refresh_token_hash  TEXT NOT NULL,
    expires_at          REAL NOT NULL,
    revoked             INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def tx():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
