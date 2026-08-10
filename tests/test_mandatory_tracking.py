"""Tests for closing the Apply-Later tracking gap on the Generator's "Save
to History" path, and for the new `resume_snapshot` field that lets
Interview Prep show exactly what resume content was sent to a company —
see docs/design-plans/2026-08-09-mandatory-application-tracking.md.
"""

import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import history  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from career import db as career_db  # noqa: E402
from career import email_link  # noqa: E402
from src.api import _tasks, app  # noqa: E402


class TestHistorySchemaMigration:
    """history.py's own DB layer, in isolation — no FastAPI involved."""

    def test_fresh_db_has_resume_snapshot_column(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "fresh.db"))
        history.init_db("resume-1")
        conn = sqlite3.connect(history.DB_PATH)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(resume_history)")}
        conn.close()
        assert "resume_snapshot" in cols

    def test_pre_existing_db_without_resume_snapshot_gets_migrated(
        self, tmp_path, monkeypatch
    ) -> None:
        db_path = tmp_path / "old.db"
        monkeypatch.setattr(history, "DB_PATH", str(db_path))
        # Simulate a database created before this column existed (jd_text
        # already present, resume_snapshot not yet).
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE resume_history ("
            "id TEXT PRIMARY KEY, resume_id TEXT, company_name TEXT NOT NULL, "
            "job_title TEXT, job_url TEXT, jd_text TEXT, pdf_path TEXT NOT NULL, "
            "ats_score REAL, verdict TEXT, applied_date TEXT, created_at REAL NOT NULL)"
        )
        conn.commit()
        conn.close()

        history.init_db("resume-1")

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(resume_history)")}
        conn.close()
        assert "resume_snapshot" in cols

    def test_save_entry_round_trips_resume_snapshot(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "rt.db"))
        history.init_db("resume-1")
        entry = history.save_entry(
            resume_id="resume-1",
            company_name="Acme Corp",
            job_title="AI Engineer",
            job_url="https://example.com/job",
            jd_text="We need a Python engineer.",
            pdf_path=str(tmp_path / "resume.pdf"),
            ats_score=90.0,
            verdict="Ready to submit",
            applied_date="",
            resume_snapshot="ABIRAMI B\nGenerative AI Developer...",
        )
        assert entry["resume_snapshot"] == "ABIRAMI B\nGenerative AI Developer..."
        fetched = history.get_entry(entry["id"])
        assert fetched is not None
        assert fetched["resume_snapshot"] == "ABIRAMI B\nGenerative AI Developer..."

    def test_save_entry_allows_null_resume_snapshot(self, tmp_path, monkeypatch) -> None:
        """Snapshot capture is non-fatal in the endpoint (see below) — the
        DB layer itself must accept None without erroring."""
        monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "null.db"))
        history.init_db("resume-1")
        entry = history.save_entry(
            resume_id="resume-1",
            company_name="Acme Corp",
            job_title="AI Engineer",
            job_url="",
            jd_text="",
            pdf_path=str(tmp_path / "resume.pdf"),
            ats_score=None,
            verdict=None,
            applied_date="",
            resume_snapshot=None,
        )
        assert entry["resume_snapshot"] is None


def _isolate_career_db(monkeypatch, tmp_path) -> None:
    """Point career.db at a fresh tmp file AND clear its thread-local
    connection cache — monkeypatching DB_PATH alone silently no-ops if this
    thread already opened a connection to the old path (the exact bug
    class the credentials test suite's docstring warns about)."""
    monkeypatch.setattr(career_db, "DB_PATH", str(tmp_path / "career-test.db"))
    monkeypatch.setattr(career_db, "_local", threading.local())
    career_db.init_db("resume-1")


class TestLinkApplyLater:
    """career/email_link.py's public `link_apply_later` wrapper — the
    entry point the Generator's Save to History now uses to close the
    gap where saving a tailored resume never touched the Application
    Tracker."""

    def test_creates_new_row_when_none_exists(self, monkeypatch, tmp_path) -> None:
        _isolate_career_db(monkeypatch, tmp_path)

        entry_id, created = email_link.link_apply_later(
            "resume-1", "Acme Corp", "AI Engineer", "https://example.com/job"
        )

        assert entry_id is not None
        assert created is True
        row = career_db.get_conn().execute(
            "SELECT status, role_title, company_name FROM apply_later WHERE id = ?",
            (entry_id,),
        ).fetchone()
        assert row["status"] == "Applied"
        assert row["role_title"] == "AI Engineer"
        assert row["company_name"] == "Acme Corp"

    def test_updates_existing_row_instead_of_duplicating(self, monkeypatch, tmp_path) -> None:
        _isolate_career_db(monkeypatch, tmp_path)

        first_id, first_created = email_link.link_apply_later(
            "resume-1", "Acme Corp", "AI Engineer", ""
        )
        second_id, second_created = email_link.link_apply_later(
            "resume-1", "Acme Corp", "Senior AI Engineer", ""
        )

        assert first_created is True
        assert second_created is False
        assert first_id == second_id

        count = career_db.get_conn().execute(
            "SELECT COUNT(*) AS c FROM apply_later WHERE resume_id = ? AND LOWER(company_name) = LOWER(?)",
            ("resume-1", "Acme Corp"),
        ).fetchone()["c"]
        assert count == 1

    def test_empty_company_name_links_nothing(self, monkeypatch, tmp_path) -> None:
        _isolate_career_db(monkeypatch, tmp_path)
        entry_id, created = email_link.link_apply_later("resume-1", "", "Role", "")
        assert entry_id is None
        assert created is False


def _seed_done_task(
    task_id: str, *, recruiter_result: dict | None, tex_path: str | None = None
) -> None:
    """Insert a minimal completed-task record matching what `_pipeline`
    leaves behind, including a compiled PDF path (required by save_history)."""
    _tasks[task_id] = {
        "status": "done",
        "resume_id": "fake-resume-id",
        "pdf_path": "/fake/path/resume.pdf",
        "tex_path": tex_path,
        "score": 88.5,
        "verdict": "Ready to submit",
        "recruiter_result": recruiter_result,
    }


class TestSaveHistoryResumeSnapshotAndApplyLater:
    """POST /api/history — the two new behaviors added on top of the
    existing jd_text/checklist behavior covered by
    test_history_and_checklist_save.py."""

    def _patch_common(self, monkeypatch, *, apply_later_result=("al-1", True)):
        saved_calls = []

        def fake_history_save(**kwargs):
            saved_calls.append(kwargs)
            return {"id": "entry-1", **kwargs}

        monkeypatch.setattr("src.api.history_save", fake_history_save)
        monkeypatch.setattr("src.api.add_checklist_topics", lambda *a, **k: [])
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", "/fake/base.tex")
        )
        monkeypatch.setattr(
            "src.api.link_apply_later", lambda *a, **k: apply_later_result
        )
        return saved_calls

    def test_resume_snapshot_uses_plain_text_not_raw_tex(self, monkeypatch) -> None:
        """Must go through parse_resume()["plain_text"] like /api/compare
        and /api/pitch — never a raw strip_latex() over the whole file
        (that path still includes the LaTeX preamble)."""
        _seed_done_task(
            "hist-snap-1", recruiter_result={"job_title": "X"}, tex_path="/fake/tailored.tex"
        )
        saved_calls = self._patch_common(monkeypatch)

        seen_paths = []

        def fake_parse_resume(path):
            seen_paths.append(path)
            return {"plain_text": "CLEAN PLAIN TEXT, NO PREAMBLE"}

        monkeypatch.setattr("src.api.parse_resume", fake_parse_resume)

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-snap-1", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        assert seen_paths == ["/fake/tailored.tex"]  # task's own tailored copy, not base
        assert saved_calls[0]["resume_snapshot"] == "CLEAN PLAIN TEXT, NO PREAMBLE"

    def test_resume_snapshot_falls_back_to_base_path_when_task_has_no_tex_path(
        self, monkeypatch
    ) -> None:
        _seed_done_task("hist-snap-2", recruiter_result={"job_title": "X"}, tex_path=None)
        saved_calls = self._patch_common(monkeypatch)

        seen_paths = []
        monkeypatch.setattr(
            "src.api.parse_resume",
            lambda path: (seen_paths.append(path), {"plain_text": "BASE TEXT"})[1],
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-snap-2", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        assert seen_paths == ["/fake/base.tex"]
        assert saved_calls[0]["resume_snapshot"] == "BASE TEXT"

    def test_snapshot_capture_failure_is_non_fatal(self, monkeypatch) -> None:
        """A resume file missing on disk (or any parse failure) must not
        prevent the history entry itself from being saved — matches the
        existing non-fatal pattern already used for checklist updates in
        this same endpoint."""
        _seed_done_task("hist-snap-3", recruiter_result={"job_title": "X"}, tex_path="/gone.tex")
        saved_calls = self._patch_common(monkeypatch)

        def boom(path):
            raise FileNotFoundError(path)

        monkeypatch.setattr("src.api.parse_resume", boom)

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-snap-3", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        assert saved_calls[0]["resume_snapshot"] is None

    def test_apply_later_linked_true_on_success(self, monkeypatch) -> None:
        _seed_done_task("hist-al-1", recruiter_result={"job_title": "X"})
        self._patch_common(monkeypatch, apply_later_result=("al-1", True))
        monkeypatch.setattr("src.api.parse_resume", lambda path: {"plain_text": ""})

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-al-1", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        assert resp.json()["apply_later_linked"] is True

    def test_apply_later_linked_true_on_update_not_just_create(self, monkeypatch) -> None:
        """created=False (an existing row was updated) is still a success —
        must not be reported as a failure to the frontend."""
        _seed_done_task("hist-al-2", recruiter_result={"job_title": "X"})
        self._patch_common(monkeypatch, apply_later_result=("al-1", False))
        monkeypatch.setattr("src.api.parse_resume", lambda path: {"plain_text": ""})

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-al-2", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        assert resp.json()["apply_later_linked"] is True

    def test_apply_later_link_failure_is_non_fatal_and_reported_false(self, monkeypatch) -> None:
        """The whole point of this feature is a reliable application
        record — if linking genuinely fails, the history entry must still
        save (non-fatal), but the response must say so honestly rather
        than silently claiming success."""
        _seed_done_task("hist-al-3", recruiter_result={"job_title": "X"})
        saved_calls = self._patch_common(monkeypatch)

        def boom(*a, **k):
            raise RuntimeError("apply_later db is on fire")

        monkeypatch.setattr("src.api.link_apply_later", boom)
        monkeypatch.setattr("src.api.parse_resume", lambda path: {"plain_text": ""})

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-al-3", "company_name": "Acme"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["apply_later_linked"] is False
        assert body["entry"]["id"] == "entry-1"  # history save still succeeded
        assert saved_calls  # history_save was still called despite the link failure
