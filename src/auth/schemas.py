"""Pydantic request models for the `/api/auth/*` endpoints."""

import re

from pydantic import BaseModel, EmailStr, field_validator

_MOBILE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")  # E.164-ish, 8-15 digits


class SignupRequest(BaseModel):
    """Body for POST /signup — name, mobile, and email are all mandatory."""

    name: str
    mobile_number: str
    email: EmailStr

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Reject a name that's empty or only whitespace."""
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("mobile_number")
    @classmethod
    def mobile_valid(cls, v: str) -> str:
        """Require an E.164-ish mobile number (8-15 digits, optional +)."""
        v = v.strip()
        if not _MOBILE_RE.match(v):
            raise ValueError("Enter a valid mobile number, e.g. +919876543210")
        return v


class OtpSendRequest(BaseModel):
    """Body for POST /otp/send."""

    mobile_number: str
    purpose: str  # "signup" | "reset"


class OtpVerifyRequest(BaseModel):
    """Body for POST /otp/verify."""

    mobile_number: str
    otp: str
    purpose: str


class PinSetRequest(BaseModel):
    """Body for POST /pin/set and /pin/reset."""

    otp_verified_token: str
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_is_4_digits(cls, v: str) -> str:
        """Require exactly 4 numeric digits."""
        if not re.match(r"^\d{4}$", v):
            raise ValueError("PIN must be exactly 4 digits")
        return v


class PinLoginRequest(BaseModel):
    """Body for POST /pin/login."""

    identifier: str  # mobile number or email
    pin: str


class CompleteMobileRequest(BaseModel):
    """Body for POST /complete-mobile."""

    otp_verified_token: str
