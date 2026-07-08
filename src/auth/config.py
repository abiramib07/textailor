import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_AUTH_DIR = Path(__file__).parent
_DATA_DIR = _AUTH_DIR / "data"
_DATA_DIR.mkdir(exist_ok=True)

DB_PATH = str(_DATA_DIR / "auth.db")

# JWT — falls back to a random secret generated at process start if unset.
# That means restarting the server invalidates old sessions until AUTH_JWT_SECRET
# is pinned in the environment — fine for dev, must be set explicitly in prod.
# IMPORTANT: with `uvicorn --reload`, the default watcher covers the whole
# project directory, including src/auth/data/auth.db — every signup/OTP/PIN
# write touches that file and would otherwise trigger a full server restart
# (and silently invalidate every session). Run with --reload-dir src to scope
# the watcher to source files only, or pass AUTH_JWT_SECRET so restarts don't
# invalidate sessions even if it does reload.
JWT_SECRET = os.environ.get("AUTH_JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
OTP_VERIFIED_TOKEN_TTL_SECONDS = 5 * 60

# OTP
OTP_LENGTH = 6
OTP_TTL_SECONDS = 5 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_VERIFY_ATTEMPTS = 5

# PIN
PIN_LENGTH = 4
PIN_MAX_FAILED_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 15 * 60

# Dev mode — when true, /api/auth endpoints echo the generated OTP back in the
# JSON response and the SMS provider just logs it, so the flow is testable
# without a real SMS gateway. MUST be false in any environment reachable by
# real users; set AUTH_DEV_MODE=false once a real SmsProvider is wired up.
DEV_MODE = os.environ.get("AUTH_DEV_MODE", "true").lower() != "false"

# Cookies — Secure requires HTTPS, so it's off by default for local http:// dev.
# Set AUTH_APP_ENV=production (and serve over HTTPS) to enable it.
IS_PRODUCTION = os.environ.get("AUTH_APP_ENV", "development") == "production"
COOKIE_SECURE = IS_PRODUCTION
COOKIE_SAMESITE = "lax"

FRONTEND_ORIGIN = os.environ.get("AUTH_FRONTEND_ORIGIN", "http://localhost:4200")
BACKEND_ORIGIN = os.environ.get("AUTH_BACKEND_ORIGIN", "http://localhost:8000")

# SMS provider selection: "console" (default, dev-only) or "twilio" (needs creds below)
SMS_PROVIDER = os.environ.get("AUTH_SMS_PROVIDER", "console")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# Google OAuth 2.1 (Authorization Code + PKCE)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", f"{BACKEND_ORIGIN}/api/auth/google/callback"
)
GOOGLE_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
