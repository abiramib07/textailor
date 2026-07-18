"""Pydantic request models for the `/api/career/*` endpoints."""

from pydantic import BaseModel


class PersonalInfoUpsert(BaseModel):
    """Body for PUT /api/career/personal-info."""

    resume_id: str
    key: str
    value: str


class ApplyLaterCreate(BaseModel):
    """Body for POST /api/career/apply-later."""

    resume_id: str
    url: str
    company_name: str = ""
    notes: str = ""


class ApplyLaterUpdate(BaseModel):
    """Body for PATCH /api/career/apply-later/{id}."""

    applied: bool | None = None
    notes: str | None = None


class JobPostCreate(BaseModel):
    """Body for POST /api/career/posts."""

    resume_id: str
    url: str = ""
    company_name: str = ""
    role_title: str = ""
    raw_text: str = ""


class InterviewTopicCreate(BaseModel):
    """Body for POST /api/career/interview-topics."""

    resume_id: str
    company_name: str
    topic: str
    github_url: str = ""
    youtube_url: str = ""
    notes: str = ""


class InterviewTopicUpdate(BaseModel):
    """Body for PATCH /api/career/interview-topics/{id}."""

    covered: bool | None = None
    github_url: str | None = None
    youtube_url: str | None = None
    notes: str | None = None
