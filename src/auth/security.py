import hashlib
import secrets
import time

import bcrypt
import jwt

from . import config


# ── PIN hashing ──────────────────────────────────────────────────────────────
def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))


# ── OTP ──────────────────────────────────────────────────────────────────────
def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(config.OTP_LENGTH))


def hash_otp(otp: str) -> str:
    # OTPs are short-lived and low-entropy by nature; a fast hash is fine here
    # (unlike the PIN, which persists indefinitely and needs bcrypt's cost factor).
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp_hash(otp: str, otp_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(otp), otp_hash)


# ── JWT access tokens ────────────────────────────────────────────────────────
def issue_access_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + config.ACCESS_TOKEN_TTL_SECONDS,
        "type": "access",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# ── Short-lived OTP-verified token (proves OTP ownership for the next step) ──
def issue_otp_verified_token(mobile_number: str, purpose: str) -> str:
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
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "otp_verified":
        return None
    return payload


# ── Refresh tokens (opaque random string; only the hash is stored server-side) ─
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
