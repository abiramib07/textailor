"""FastAPI routes for `/api/credentials/*`: encrypted job-account
credentials (email/password per company account), scoped to a resume
identity. Mounted into the main app by `src.api`.

Every route requires a valid login session — unlike `career`/`resumes`,
which are unguarded today, this is the first feature storing real secrets
rather than notes/URLs, so it gets the stronger default. The app's
Angular root is already gated behind login (`auth.guard.ts`), so this
costs nothing UX-wise — a session cookie always exists by the time any
tab renders.
"""

import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from auth.router import get_current_user

from . import crypto
from .db import get_conn, tx
from .schemas import CredentialCreate, CredentialUpdate

router = APIRouter(
    prefix="/api/credentials", tags=["credentials"], dependencies=[Depends(get_current_user)]
)

_UPDATE_TEXT_FIELDS = ("company_name", "site_url", "login_email", "username", "notes")


def _row_to_entry(row: sqlite3.Row) -> dict:
    """Map a `credentials` row to the public shape — never includes the
    encrypted or plaintext password, only whether one is set."""
    data = dict(row)
    has_password = bool(data.pop("password_enc", None))
    return {**data, "has_password": has_password}


@router.post("")
def create_credential(req: CredentialCreate) -> dict:
    """Save a new job-account credential, encrypting the password before storage."""
    if not req.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name is required")
    if not req.login_email.strip():
        raise HTTPException(status_code=400, detail="Login email is required")
    if not req.password:
        raise HTTPException(status_code=400, detail="Password is required")

    entry_id = str(uuid.uuid4())
    now = time.time()
    with tx() as conn:
        conn.execute(
            "INSERT INTO credentials (id, resume_id, company_name, site_url, login_email, "
            "username, password_enc, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id,
                req.resume_id,
                req.company_name.strip(),
                req.site_url.strip(),
                req.login_email.strip(),
                req.username.strip(),
                crypto.encrypt(req.password),
                req.notes.strip(),
                now,
                now,
            ),
        )
    return _get_credential(entry_id)


@router.get("")
def list_credentials(resume_id: str) -> dict:
    """List every saved job-account credential for a resume identity, newest
    first. Passwords are never included — only `has_password`."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM credentials WHERE resume_id = ? ORDER BY created_at DESC", (resume_id,)
    ).fetchall()
    return {"entries": [_row_to_entry(r) for r in rows]}


@router.get("/{entry_id}/reveal")
def reveal_credential(entry_id: str) -> dict:
    """Decrypt and return one credential's password — only called when the
    user explicitly clicks "Show", never as part of the list response."""
    row = (
        get_conn()
        .execute("SELECT password_enc FROM credentials WHERE id = ?", (entry_id,))
        .fetchone()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"password": crypto.decrypt(row["password_enc"])}


@router.patch("/{entry_id}")
def update_credential(entry_id: str, req: CredentialUpdate) -> dict:
    """Update only the fields provided; `password` is re-encrypted only if given."""
    existing = get_conn().execute("SELECT id FROM credentials WHERE id = ?", (entry_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Credential not found")

    with tx() as conn:
        for field in _UPDATE_TEXT_FIELDS:
            value = getattr(req, field)
            if value is not None:
                conn.execute(
                    f"UPDATE credentials SET {field} = ? WHERE id = ?", (value.strip(), entry_id)
                )
        if req.password is not None:
            conn.execute(
                "UPDATE credentials SET password_enc = ? WHERE id = ?",
                (crypto.encrypt(req.password), entry_id),
            )
        conn.execute("UPDATE credentials SET updated_at = ? WHERE id = ?", (time.time(), entry_id))
    return _get_credential(entry_id)


@router.delete("/{entry_id}")
def delete_credential(entry_id: str) -> dict:
    """Remove a saved job-account credential."""
    with tx() as conn:
        conn.execute("DELETE FROM credentials WHERE id = ?", (entry_id,))
    return {"ok": True}


def _get_credential(entry_id: str) -> dict:
    row = get_conn().execute("SELECT * FROM credentials WHERE id = ?", (entry_id,)).fetchone()
    return {"entry": _row_to_entry(row) if row else None}
