"""Google OAuth 2.1 helpers (Authorization Code + PKCE) used by
`auth.router`'s `/google/login` and `/google/callback` routes.
"""

import secrets
from urllib.parse import urlencode

import httpx

from . import config

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


def build_authorize_url(state: str, code_challenge: str) -> str:
    """Build the Google consent-screen URL for a PKCE authorization request."""
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def new_pkce_verifier() -> str:
    """Generate a PKCE code verifier (43-128 chars per RFC 7636)."""
    return secrets.token_urlsafe(64)[:128]


def exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange an authorization code for Google access/ID tokens."""
    resp = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    """Fetch the Google profile (sub, email, name) for an access token."""
    resp = httpx.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
