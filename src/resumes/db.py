"""SQLite schema and connection management for resume identities.

Each row is one resume "identity" (yours, or someone else's) with its own
`.tex` file on disk. The rest of the app (pipeline, history, career tools,
email patterns) scopes its data to a `resume_id` resolved here, so multiple
people's resumes can be tailored through the same tool without mixing data.
"""

import shutil
import sqlite3
import time
import uuid
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "resumes.db")

_RESUME_ROOT = Path(__file__).parent.parent.parent / "resume"

SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    id           TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    owner_name   TEXT NOT NULL DEFAULT '',
    tex_path     TEXT NOT NULL,
    is_default   INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    """Open a fresh connection to resumes.db."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(default_tex_path: str) -> None:
    """Create the resumes table, seeding one default row that wraps the
    existing base resume (`default_tex_path`) the first time this runs."""
    conn = _conn()
    conn.executescript(SCHEMA)
    conn.commit()
    existing = conn.execute("SELECT COUNT(*) AS n FROM resumes").fetchone()["n"]
    if existing == 0:
        conn.execute(
            "INSERT INTO resumes (id, label, owner_name, tex_path, is_default, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (str(uuid.uuid4()), "My Resume", "", default_tex_path, time.time()),
        )
        conn.commit()
    conn.close()


def list_resumes() -> list[dict]:
    """Return every resume identity, default first then oldest first."""
    conn = _conn()
    rows = conn.execute("SELECT * FROM resumes ORDER BY is_default DESC, created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_resume(resume_id: str) -> dict | None:
    """Look up one resume identity by id, or None if it doesn't exist."""
    conn = _conn()
    row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_default_resume() -> dict:
    """Return the default resume row (always exists once `init_db` has run)."""
    conn = _conn()
    row = conn.execute("SELECT * FROM resumes WHERE is_default = 1 LIMIT 1").fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("Default resume missing — was init_db() called at startup?")
    return dict(row)


def resolve_resume_id(resume_id: str | None) -> str:
    """Return `resume_id` if given, else the default resume's id."""
    return resume_id if resume_id else get_default_resume()["id"]


def create_resume(label: str, owner_name: str, tex_content: str) -> dict:
    """Create a new resume identity with its own `.tex` file on disk."""
    resume_id = str(uuid.uuid4())
    resume_dir = _RESUME_ROOT / resume_id
    resume_dir.mkdir(parents=True, exist_ok=True)
    tex_path = resume_dir / "main.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    conn = _conn()
    conn.execute(
        "INSERT INTO resumes (id, label, owner_name, tex_path, is_default, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (resume_id, label.strip(), owner_name.strip(), str(tex_path), time.time()),
    )
    conn.commit()
    conn.close()
    resume = get_resume(resume_id)
    assert resume is not None, "just-inserted resume must exist"
    return resume


def update_resume(resume_id: str, label: str | None, owner_name: str | None) -> dict | None:
    """Rename a resume identity and/or update its owner name."""
    conn = _conn()
    existing = conn.execute("SELECT id FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    if label is not None:
        conn.execute("UPDATE resumes SET label = ? WHERE id = ?", (label.strip(), resume_id))
    if owner_name is not None:
        conn.execute(
            "UPDATE resumes SET owner_name = ? WHERE id = ?", (owner_name.strip(), resume_id)
        )
    conn.commit()
    conn.close()
    return get_resume(resume_id)


def delete_resume(resume_id: str) -> bool:
    """Delete a non-default resume identity and its `.tex` folder.

    Returns False (no-op) for an unknown id or the default resume, which
    can never be deleted.
    """
    resume = get_resume(resume_id)
    if not resume or resume["is_default"]:
        return False
    conn = _conn()
    conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    conn.commit()
    conn.close()
    resume_dir = Path(resume["tex_path"]).parent
    if resume_dir.exists() and resume_dir != _RESUME_ROOT:
        shutil.rmtree(resume_dir, ignore_errors=True)
    return True
