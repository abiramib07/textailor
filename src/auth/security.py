"""Cryptographic primitives for the auth module: bcrypt PIN hashing, SHA-256
OTP hashing, and JWT issuance/verification for access, OTP-verified, and
refresh tokens.
"""

import hashlib
import secrets
import time

import bcrypt
import jwt

from . import config


# ── PIN hashing ──────────────────────────────────────────────────────────────
def hash_pin(pin: str) -> str:
    """Bcrypt-hash a 4-digit PIN for storage."""
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Check a submitted PIN against its stored bcrypt hash."""
    return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))


# ── OTP ──────────────────────────────────────────────────────────────────────
def generate_otp() -> str:
    """Generate a random numeric OTP of `config.OTP_LENGTH` digits."""
    return "".join(secrets.choice("0123456789") for _ in range(config.OTP_LENGTH))


def hash_otp(otp: str) -> str:
    """SHA-256 hash an OTP for storage.

    OTPs are short-lived and low-entropy by nature; a fast hash is fine here
    (unlike the PIN, which persists indefinitely and needs bcrypt's cost factor).
    """
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp_hash(otp: str, otp_hash: str) -> bool:
    """Constant-time check of a submitted OTP against its stored hash."""
    return secrets.compare_digest(hash_otp(otp), otp_hash)


# ── JWT access tokens ────────────────────────────────────────────────────────
def issue_access_token(user_id: str) -> str:
    """Issue a short-lived JWT access token for a user."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + config.ACCESS_TOKEN_TTL_SECONDS,
        "type": "access",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate an access token, returning None if invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# ── Short-lived OTP-verified token (proves OTP ownership for the next step) ──
def issue_otp_verified_token(mobile_number: str, purpose: str) -> str:
    """Issue a short-lived token proving OTP ownership, scoped to one purpose
    (signup / reset / complete_profile) so it can't be replayed for another."""
    now = int(time.time())
    payload = {
        "mobile_number": mobile_number,
        "purpose": purpose,
        "iat": now,
        "exp": now + config.OTP_VERIFIED_TOKEN_TTL_SECONDS,
        "type": "otp_verified",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_otp_verified_token(token: str) -> dict | None:
    """Decode and validate an OTP-verified token, returning None if invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "otp_verified":
        return None
    return payload


# ── Refresh tokens (opaque random string; only the hash is stored server-side) ─
def generate_refresh_token() -> str:
    """Generate an opaque random refresh token (not a JWT — just stored hashed)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash a refresh token for storage/lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
