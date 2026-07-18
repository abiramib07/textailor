"""Pydantic request models for the `/api/resumes` endpoints."""

from pydantic import BaseModel


class ResumeUpdate(BaseModel):
    """Body for PATCH /api/resumes/{id}."""

    label: str | None = None
    owner_name: str | None = None
