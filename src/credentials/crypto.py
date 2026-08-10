"""Reversible symmetric encryption for stored job-account passwords.

Unlike the auth module's PIN/OTP hashing (deliberately one-way), the whole
point of this feature is to decrypt a stored password back to plaintext
for display, so it uses Fernet (authenticated AES128-CBC + HMAC) instead
of bcrypt/SHA-256.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Where the encryption key is persisted if CREDENTIALS_ENC_KEY isn't set.
# Deliberately NOT regenerated per process (unlike auth.config.JWT_SECRET's
# random-per-process dev fallback) — losing this key permanently bricks
# every stored password, unlike a JWT secret rotation which just logs
# sessions out. Set CREDENTIALS_ENC_KEY explicitly and back it up outside
# the repo for anything beyond local dev.
KEY_PATH = _DATA_DIR / ".enc_key"

_fernet: Fernet | None = None


def _load_or_create_key(key_path: Path = KEY_PATH) -> bytes:
    """Return the Fernet key: `CREDENTIALS_ENC_KEY` env var if set, else the
    key persisted at `key_path`, generating and persisting one on first use."""
    env_key = os.environ.get("CREDENTIALS_ENC_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def _get_fernet() -> Fernet:
    """Return the process-wide Fernet instance, initializing it on first use."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key(KEY_PATH))
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext password for storage."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a stored password token back to plaintext.

    Raises `cryptography.fernet.InvalidToken` if `token` is malformed or
    was encrypted under a different key.
    """
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
