import logging
import time
import uuid
from base64 import urlsafe_b64encode
from hashlib import sha256

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from . import config, google_oauth, security
from .db import get_conn, tx
from .schemas import (
    CompleteMobileRequest,
    OtpSendRequest,
    OtpVerifyRequest,
    PinLoginRequest,
    PinSetRequest,
    SignupRequest,
)
from .sms import get_sms_provider

log = logging.getLogger("textailor.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"

# Short-lived Google OAuth state — a redirect flow has no session yet to store
# the PKCE verifier in, so it's held here in memory and popped on callback.
_oauth_states: dict = {}
_OAUTH_STATE_TTL = 10 * 60


# ── helpers ───────────────────────────────────────────────────────────────────
def _user_row_to_profile(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "mobile_number": row["mobile_number"],
        "mobile_verified": bool(row["mobile_verified"]),
        "has_pin": row["pin_hash"] is not None,
        "google_linked": row["google_sub"] is not None,
    }


def _set_session_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=config.ACCESS_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=config.REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


def _issue_session(response: Response, user_id: str) -> None:
    access_token = security.issue_access_token(user_id)
    refresh_token = security.generate_refresh_token()
    with tx() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at, revoked, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (
                str(uuid.uuid4()),
                user_id,
                security.hash_refresh_token(refresh_token),
                time.time() + config.REFRESH_TOKEN_TTL_SECONDS,
                time.time(),
            ),
        )
    _set_session_cookies(response, access_token, refresh_token)


def get_current_user(
    request: Request,
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
):
    token = access_token
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = security.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return row


def _check_otp_cooldown(mobile_number: str, purpose: str):
    conn = get_conn()
    last = conn.execute(
        "SELECT created_at FROM otp_requests WHERE mobile_number = ? AND purpose = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (mobile_number, purpose),
    ).fetchone()
    if last and time.time() - last["created_at"] < config.OTP_RESEND_COOLDOWN_SECONDS:
        wait = int(config.OTP_RESEND_COOLDOWN_SECONDS - (time.time() - last["created_at"]))
        raise HTTPException(status_code=429, detail=f"Please wait {wait}s before requesting another code")


def _send_otp(mobile_number: str, purpose: str) -> str | None:
    _check_otp_cooldown(mobile_number, purpose)
    otp = security.generate_otp()
    with tx() as conn:
        conn.execute(
            "UPDATE otp_requests SET consumed = 1 WHERE mobile_number = ? AND purpose = ? AND consumed = 0",
            (mobile_number, purpose),
        )
        conn.execute(
            "INSERT INTO otp_requests (id, mobile_number, purpose, otp_hash, expires_at, attempts, consumed, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
            (
                str(uuid.uuid4()),
                mobile_number,
                purpose,
                security.hash_otp(otp),
                time.time() + config.OTP_TTL_SECONDS,
                time.time(),
            ),
        )
    get_sms_provider().send_otp(mobile_number, otp)
    return otp if config.DEV_MODE else None


# ── Signup ───────────────────────────────────────────────────────────────────
@router.post("/signup")
def signup(req: SignupRequest):
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM users WHERE email = ? OR mobile_number = ?",
        (req.email, req.mobile_number),
    ).fetchone()

    if existing and existing["pin_hash"] is not None:
        raise HTTPException(status_code=409, detail="An account with this email or mobile number already exists")

    if existing:
        # Incomplete signup (OTP/PIN never finished) — resume it rather than 409ing.
        with tx() as conn:
            conn.execute(
                "UPDATE users SET name = ?, email = ?, mobile_number = ? WHERE id = ?",
                (req.name, req.email, req.mobile_number, existing["id"]),
            )
    else:
        with tx() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, mobile_number, mobile_verified, pin_hash, google_sub, "
                "failed_pin_attempts, locked_until, created_at) VALUES (?, ?, ?, ?, 0, NULL, NULL, 0, NULL, ?)",
                (str(uuid.uuid4()), req.name, req.email, req.mobile_number, time.time()),
            )

    dev_otp = _send_otp(req.mobile_number, "signup")
    return {"mobile_number": req.mobile_number, "message": "OTP sent", "dev_otp": dev_otp}


# ── OTP send / verify (shared by signup + forgot-pin + complete-profile) ─────
@router.post("/otp/send")
def otp_send(req: OtpSendRequest):
    conn = get_conn()
    if req.purpose == "signup":
        user = conn.execute(
            "SELECT * FROM users WHERE mobile_number = ? AND pin_hash IS NULL", (req.mobile_number,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=400, detail="Start signup first")
    elif req.purpose == "reset":
        user = conn.execute(
            "SELECT * FROM users WHERE mobile_number = ? AND pin_hash IS NOT NULL", (req.mobile_number,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="No account found for this mobile number")
    elif req.purpose == "complete_profile":
        taken = conn.execute("SELECT id FROM users WHERE mobile_number = ?", (req.mobile_number,)).fetchone()
        if taken:
            raise HTTPException(status_code=409, detail="This mobile number is already in use")
    else:
        raise HTTPException(status_code=400, detail="Unknown purpose")

    dev_otp = _send_otp(req.mobile_number, req.purpose)
    return {"message": "OTP sent", "dev_otp": dev_otp}


@router.post("/otp/verify")
def otp_verify(req: OtpVerifyRequest):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM otp_requests WHERE mobile_number = ? AND purpose = ? AND consumed = 0 "
        "ORDER BY created_at DESC LIMIT 1",
        (req.mobile_number, req.purpose),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="No pending code — request a new one")
    if row["expires_at"] < time.time():
        raise HTTPException(status_code=400, detail="Code expired — request a new one")
    if row["attempts"] >= config.OTP_MAX_VERIFY_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many incorrect attempts — request a new code")

    if not security.verify_otp_hash(req.otp, row["otp_hash"]):
        with tx() as conn:
            conn.execute("UPDATE otp_requests SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        remaining = config.OTP_MAX_VERIFY_ATTEMPTS - row["attempts"] - 1
        raise HTTPException(status_code=400, detail=f"Incorrect code — {remaining} attempt(s) left")

    with tx() as conn:
        conn.execute("UPDATE otp_requests SET consumed = 1 WHERE id = ?", (row["id"],))
        if req.purpose == "signup":
            conn.execute(
                "UPDATE users SET mobile_verified = 1 WHERE mobile_number = ?", (req.mobile_number,)
            )

    token = security.issue_otp_verified_token(req.mobile_number, req.purpose)
    return {"otp_verified_token": token}


# ── PIN setup (end of signup) ────────────────────────────────────────────────
@router.post("/pin/set")
def pin_set(req: PinSetRequest, response: Response):
    payload = security.decode_otp_verified_token(req.otp_verified_token)
    if not payload or payload["purpose"] != "signup":
        raise HTTPException(status_code=401, detail="Verification expired — start signup again")

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE mobile_number = ? AND mobile_verified = 1", (payload["mobile_number"],)
    ).fetchone()
    if not user:
        raise HTTPException(status_code=400, detail="Mobile number not verified")
    if user["pin_hash"] is not None:
        raise HTTPException(status_code=409, detail="PIN already set — please log in")

    with tx() as conn:
        conn.execute("UPDATE users SET pin_hash = ? WHERE id = ?", (security.hash_pin(req.pin), user["id"]))

    _issue_session(response, user["id"])
    user = get_conn().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": _user_row_to_profile(user)}


# ── Forgot-PIN reset ──────────────────────────────────────────────────────────
@router.post("/pin/reset")
def pin_reset(req: PinSetRequest, response: Response):
    payload = security.decode_otp_verified_token(req.otp_verified_token)
    if not payload or payload["purpose"] != "reset":
        raise HTTPException(status_code=401, detail="Verification expired — request a new code")

    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE mobile_number = ?", (payload["mobile_number"],)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")

    with tx() as conn:
        conn.execute(
            "UPDATE users SET pin_hash = ?, failed_pin_attempts = 0, locked_until = NULL WHERE id = ?",
            (security.hash_pin(req.pin), user["id"]),
        )

    _issue_session(response, user["id"])
    user = get_conn().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": _user_row_to_profile(user)}


# ── PIN login ─────────────────────────────────────────────────────────────────
@router.post("/pin/login")
def pin_login(req: PinLoginRequest, response: Response):
    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE (mobile_number = ? OR email = ?) AND pin_hash IS NOT NULL",
        (req.identifier, req.identifier),
    ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user["locked_until"] and user["locked_until"] > time.time():
        wait = int(user["locked_until"] - time.time())
        raise HTTPException(status_code=423, detail=f"Account locked — try again in {wait}s")

    if not security.verify_pin(req.pin, user["pin_hash"]):
        attempts = user["failed_pin_attempts"] + 1
        locked_until = time.time() + config.PIN_LOCKOUT_SECONDS if attempts >= config.PIN_MAX_FAILED_ATTEMPTS else None
        with tx() as conn:
            conn.execute(
                "UPDATE users SET failed_pin_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, locked_until, user["id"]),
            )
        if locked_until:
            raise HTTPException(status_code=423, detail="Too many incorrect attempts — account locked for 15 minutes")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    with tx() as conn:
        conn.execute(
            "UPDATE users SET failed_pin_attempts = 0, locked_until = NULL WHERE id = ?", (user["id"],)
        )

    _issue_session(response, user["id"])
    return {"user": _user_row_to_profile(user)}


# ── Google OAuth 2.1 (Authorization Code + PKCE) ─────────────────────────────
@router.get("/google/login")
def google_login():
    if not config.GOOGLE_CONFIGURED:
        raise HTTPException(
            status_code=501,
            detail="Google login is not configured — set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET",
        )
    state = security.generate_refresh_token()
    verifier = google_oauth.new_pkce_verifier()
    challenge = urlsafe_b64encode(sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    _oauth_states[state] = {"verifier": verifier, "created_at": time.time()}
    return RedirectResponse(google_oauth.build_authorize_url(state, challenge))


@router.get("/google/callback")
def google_callback(code: str = "", state: str = "", error: str = ""):
    def _fail(reason: str):
        return RedirectResponse(f"{config.FRONTEND_ORIGIN}/auth/callback?status=error&reason={reason}")

    if error:
        return _fail("google_denied")

    entry = _oauth_states.pop(state, None)
    if not entry or time.time() - entry["created_at"] > _OAUTH_STATE_TTL:
        return _fail("state_expired")

    try:
        tokens = google_oauth.exchange_code(code, entry["verifier"])
        userinfo = google_oauth.fetch_userinfo(tokens["access_token"])
    except Exception:
        log.exception("Google OAuth exchange failed")
        return _fail("exchange_failed")

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or email
    if not sub or not email:
        return _fail("missing_profile")

    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
    if not user:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            with tx() as conn:
                conn.execute("UPDATE users SET google_sub = ? WHERE id = ?", (sub, user["id"]))
        else:
            new_id = str(uuid.uuid4())
            with tx() as conn:
                conn.execute(
                    "INSERT INTO users (id, name, email, mobile_number, mobile_verified, pin_hash, google_sub, "
                    "failed_pin_attempts, locked_until, created_at) VALUES (?, ?, ?, NULL, 0, NULL, ?, 0, NULL, ?)",
                    (new_id, name, email, sub, time.time()),
                )
            user = conn.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()

    redirect = RedirectResponse(f"{config.FRONTEND_ORIGIN}/auth/callback?status=success")
    _issue_session(redirect, user["id"])
    return redirect


# ── Complete profile (mandatory mobile number for Google-only signups) ──────
@router.post("/complete-mobile")
def complete_mobile(req: CompleteMobileRequest, user=Depends(get_current_user)):
    payload = security.decode_otp_verified_token(req.otp_verified_token)
    if not payload or payload["purpose"] != "complete_profile":
        raise HTTPException(status_code=401, detail="Verification expired — request a new code")

    conn = get_conn()
    taken = conn.execute(
        "SELECT id FROM users WHERE mobile_number = ? AND id != ?", (payload["mobile_number"], user["id"])
    ).fetchone()
    if taken:
        raise HTTPException(status_code=409, detail="This mobile number is already in use")

    with tx() as conn:
        conn.execute(
            "UPDATE users SET mobile_number = ?, mobile_verified = 1 WHERE id = ?",
            (payload["mobile_number"], user["id"]),
        )
    user = get_conn().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": _user_row_to_profile(user)}


# ── Session ───────────────────────────────────────────────────────────────────
@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"user": _user_row_to_profile(user)}


@router.post("/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_hash = security.hash_refresh_token(refresh_token)
    conn = get_conn()
    session = conn.execute(
        "SELECT * FROM sessions WHERE refresh_token_hash = ? AND revoked = 0", (token_hash,)
    ).fetchone()
    if not session or session["expires_at"] < time.time():
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired — please log in again")

    with tx() as conn:
        conn.execute("UPDATE sessions SET revoked = 1 WHERE id = ?", (session["id"],))

    _issue_session(response, session["user_id"])
    return {"ok": True}


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)):
    if refresh_token:
        token_hash = security.hash_refresh_token(refresh_token)
        with tx() as conn:
            conn.execute("UPDATE sessions SET revoked = 1 WHERE refresh_token_hash = ?", (token_hash,))
    _clear_session_cookies(response)
    return {"ok": True}
