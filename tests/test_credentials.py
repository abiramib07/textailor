"""Tests for the Job-Site Account Credentials feature
(`docs/design-plans/2026-08-09-job-account-credentials.md`):

- `src/credentials/crypto.py`   — Fernet encrypt/decrypt + persisted key
- `src/credentials/db.py`       — schema/connection management
- `/api/credentials/*`          — CRUD + reveal, gated behind login

Written before the implementation exists (design → review → tests →
implement, per the workflow for this feature) — every test in
`TestCredentialsRouter` is expected to fail with an import/collection
error until `src/credentials/` is built out to match the design doc.

DB isolation: `credentials.db` and `auth.db` both cache one SQLite
connection per thread (`threading.local()`), so simply monkeypatching
`DB_PATH` is not enough within a single pytest process — a leftover
connection from an earlier test would keep pointing at the old file. Each
test resets the module's `_local` to a fresh `threading.local()` in
addition to patching `DB_PATH`, forcing a new connection to the test's
`tmp_path` database.
"""

import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import auth.config as auth_config  # noqa: E402
import auth.db as auth_db  # noqa: E402
import auth.security as auth_security  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api import app  # noqa: E402

try:
    import credentials.crypto as cred_crypto
    import credentials.db as cred_db
except ImportError:  # pragma: no cover - expected until the module is built
    cred_crypto = None  # type: ignore[assignment]
    cred_db = None  # type: ignore[assignment]


def _isolate_db(monkeypatch, module, db_path: Path) -> None:
    """Point `module.DB_PATH` at a fresh tmp file and clear its thread-local
    connection cache so the next `get_conn()` call actually opens it."""
    monkeypatch.setattr(module, "DB_PATH", str(db_path))
    monkeypatch.setattr(module, "_local", threading.local())


def _seed_user(email: str = "candidate@example.com") -> str:
    """Insert a minimal user row directly into the (already isolated)
    auth DB and return its id — bypasses the OTP/PIN signup flow, which
    is irrelevant to what these tests are checking."""
    user_id = str(uuid.uuid4())
    conn = auth_db.get_conn()
    conn.execute(
        "INSERT INTO users (id, name, email, mobile_verified, failed_pin_attempts, created_at) "
        "VALUES (?, ?, ?, 0, 0, ?)",
        (user_id, "Test Candidate", email, time.time()),
    )
    conn.commit()
    return user_id


def _auth_headers(user_id: str) -> dict:
    """Bearer header carrying a real, freshly-issued access token for `user_id`."""
    return {"Authorization": f"Bearer {auth_security.issue_access_token(user_id)}"}


@pytest.fixture
def isolated_auth(monkeypatch, tmp_path):
    """Fresh, empty auth DB for one test. `DB_PATH` lives on `auth.config`
    but the thread-local connection cache lives on `auth.db` — unlike the
    credentials module, where both live in the same file."""
    monkeypatch.setattr(auth_config, "DB_PATH", str(tmp_path / "auth-test.db"))
    monkeypatch.setattr(auth_db, "_local", threading.local())


@pytest.fixture
def isolated_credentials(monkeypatch, tmp_path):
    """Fresh, empty credentials DB for one test."""
    assert cred_db is not None, "src/credentials/db.py does not exist yet"
    _isolate_db(monkeypatch, cred_db, tmp_path / "credentials-test.db")


# ── crypto.py ────────────────────────────────────────────────────────────────
class TestCredentialsCrypto:
    """`src/credentials/crypto.py` — Fernet round-trip and key persistence."""

    def test_module_exists(self) -> None:
        assert cred_crypto is not None, "src/credentials/crypto.py does not exist yet"

    def test_encrypt_decrypt_round_trip(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(cred_crypto, "KEY_PATH", tmp_path / "key")
        monkeypatch.setattr(cred_crypto, "_fernet", None)
        token = cred_crypto.encrypt("hunter2")
        assert token != "hunter2"  # never stored as plaintext
        assert cred_crypto.decrypt(token) == "hunter2"

    def test_tampered_ciphertext_is_rejected(self, monkeypatch, tmp_path) -> None:
        from cryptography.fernet import InvalidToken

        monkeypatch.setattr(cred_crypto, "KEY_PATH", tmp_path / "key")
        monkeypatch.setattr(cred_crypto, "_fernet", None)
        token = cred_crypto.encrypt("hunter2")
        tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
        with pytest.raises(InvalidToken):
            cred_crypto.decrypt(tampered)

    def test_key_is_persisted_to_disk_not_regenerated_per_process(
        self, monkeypatch, tmp_path
    ) -> None:
        """Simulates a server restart: the in-memory `_fernet` singleton is
        cleared (as it would be on a fresh process) but `KEY_PATH` points at
        the same file. A value encrypted "before the restart" must still
        decrypt "after" it — proving the key survives process restarts via
        the persisted file, not just an in-memory/env-var fallback."""
        key_path = tmp_path / "key"
        monkeypatch.setattr(cred_crypto, "KEY_PATH", key_path)
        monkeypatch.setattr(cred_crypto, "_fernet", None)

        token = cred_crypto.encrypt("hunter2")
        assert key_path.exists()  # the key itself must have been written to disk

        monkeypatch.setattr(cred_crypto, "_fernet", None)  # simulate restart
        assert cred_crypto.decrypt(token) == "hunter2"

    def test_env_var_key_takes_priority_over_persisted_file(self, monkeypatch, tmp_path) -> None:
        from cryptography.fernet import Fernet

        stale_file_key = Fernet.generate_key()
        (tmp_path / "key").write_bytes(stale_file_key)
        real_key = Fernet.generate_key()
        monkeypatch.setattr(cred_crypto, "KEY_PATH", tmp_path / "key")
        monkeypatch.setattr(cred_crypto, "_fernet", None)
        monkeypatch.setenv("CREDENTIALS_ENC_KEY", real_key.decode("utf-8"))

        token = Fernet(real_key).encrypt(b"hunter2").decode("utf-8")
        assert cred_crypto.decrypt(token) == "hunter2"


# ── /api/credentials/* ─────────────────────────────────────────────────────
class TestCredentialsRouter:
    """HTTP behavior of `/api/credentials/*` — CRUD, reveal, scoping, auth gate."""

    def _create(self, client, headers, **overrides) -> dict:
        body = {
            "resume_id": "resume-1",
            "company_name": "Acme Corp",
            "site_url": "https://acme.example/careers",
            "login_email": "me@example.com",
            "username": "",
            "password": "hunter2",
            "notes": "",
        }
        body.update(overrides)
        resp = client.post("/api/credentials", json=body, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()["entry"]

    def test_every_route_requires_a_session(self, isolated_auth, isolated_credentials) -> None:
        with TestClient(app) as client:
            assert client.get("/api/credentials", params={"resume_id": "resume-1"}).status_code == 401
            assert (
                client.post(
                    "/api/credentials",
                    json={
                        "resume_id": "resume-1",
                        "company_name": "Acme",
                        "login_email": "a@b.com",
                        "password": "x",
                    },
                ).status_code
                == 401
            )
            assert client.get("/api/credentials/does-not-exist/reveal").status_code == 401
            assert client.patch("/api/credentials/does-not-exist", json={}).status_code == 401
            assert client.delete("/api/credentials/does-not-exist").status_code == 401

    def test_create_then_list_never_exposes_the_password(
        self, isolated_auth, isolated_credentials
    ) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            self._create(client, headers)

            resp = client.get(
                "/api/credentials", params={"resume_id": "resume-1"}, headers=headers
            )
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["company_name"] == "Acme Corp"
        assert entry["has_password"] is True
        raw_body = resp.text
        assert "hunter2" not in raw_body
        assert "password_enc" not in entry
        assert "password" not in entry

    def test_reveal_returns_the_correct_plaintext(
        self, isolated_auth, isolated_credentials
    ) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            entry = self._create(client, headers, password="s3cret!")

            resp = client.get(f"/api/credentials/{entry['id']}/reveal", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["password"] == "s3cret!"

    def test_reveal_unknown_id_is_404(self, isolated_auth, isolated_credentials) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            resp = client.get("/api/credentials/does-not-exist/reveal", headers=headers)
        assert resp.status_code == 404

    def test_updating_notes_leaves_password_unchanged(
        self, isolated_auth, isolated_credentials
    ) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            entry = self._create(client, headers, password="original-pw")

            patch_resp = client.patch(
                f"/api/credentials/{entry['id']}",
                json={"notes": "applied 2026-08-09"},
                headers=headers,
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["entry"]["notes"] == "applied 2026-08-09"

            reveal_resp = client.get(f"/api/credentials/{entry['id']}/reveal", headers=headers)
        assert reveal_resp.json()["password"] == "original-pw"

    def test_updating_password_reencrypts(self, isolated_auth, isolated_credentials) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            entry = self._create(client, headers, password="original-pw")

            client.patch(
                f"/api/credentials/{entry['id']}",
                json={"password": "new-pw"},
                headers=headers,
            )
            reveal_resp = client.get(f"/api/credentials/{entry['id']}/reveal", headers=headers)
        assert reveal_resp.json()["password"] == "new-pw"

    def test_delete_removes_the_entry(self, isolated_auth, isolated_credentials) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            entry = self._create(client, headers)

            del_resp = client.delete(f"/api/credentials/{entry['id']}", headers=headers)
            assert del_resp.status_code == 200

            list_resp = client.get(
                "/api/credentials", params={"resume_id": "resume-1"}, headers=headers
            )
            reveal_resp = client.get(f"/api/credentials/{entry['id']}/reveal", headers=headers)
        assert list_resp.json()["entries"] == []
        assert reveal_resp.status_code == 404

    def test_list_is_scoped_to_resume_id(self, isolated_auth, isolated_credentials) -> None:
        with TestClient(app) as client:
            user_id = _seed_user()
            headers = _auth_headers(user_id)
            self._create(client, headers, resume_id="resume-1", company_name="For Resume 1")
            self._create(client, headers, resume_id="resume-2", company_name="For Resume 2")

            resp_1 = client.get(
                "/api/credentials", params={"resume_id": "resume-1"}, headers=headers
            )
            resp_2 = client.get(
                "/api/credentials", params={"resume_id": "resume-2"}, headers=headers
            )
        assert [e["company_name"] for e in resp_1.json()["entries"]] == ["For Resume 1"]
        assert [e["company_name"] for e in resp_2.json()["entries"]] == ["For Resume 2"]
