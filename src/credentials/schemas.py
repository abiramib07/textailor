"""Pydantic request models for the `/api/credentials/*` endpoints."""

from pydantic import BaseModel


class CredentialCreate(BaseModel):
    """Body for POST /api/credentials."""

    resume_id: str
    company_name: str
    site_url: str = ""
    login_email: str
    username: str = ""
    password: str
    notes: str = ""


class CredentialUpdate(BaseModel):
    """Body for PATCH /api/credentials/{id}. Only fields provided are updated;
    `password` is re-encrypted only when explicitly given."""

    company_name: str | None = None
    site_url: str | None = None
    login_email: str | None = None
    username: str | None = None
    password: str | None = None
    notes: str | None = None
