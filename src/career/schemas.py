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
    tier: str = ""
    role_title: str = ""


class ApplyLaterSearch(BaseModel):
    """Body for POST /api/career/apply-later/search."""

    resume_id: str
    query: str
    years_experience: int = 0
    location: str = "India"
    count: int = 15
    min_salary_lpa: int | None = None


class ApplyLaterUpdate(BaseModel):
    """Body for PATCH /api/career/apply-later/{id}. Only fields provided are updated."""

    applied: bool | None = None
    notes: str | None = None
    tier: str | None = None
    role_title: str | None = None
    status: str | None = None
    referral: str | None = None
    date_applied: str | None = None
    next_follow_up: str | None = None
    interview_round: str | None = None
    salary_discussed: str | None = None


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


class SeedSkillsRequest(BaseModel):
    """Body for POST /api/career/interview-topics/seed-skills."""

    resume_id: str
    company_name: str
