"""Tests for the Generator tab's "Save to History" action gaining two new
behaviors: persisting the JD text alongside the entry (`jd_text` column on
`resume_history`), and adding this task's JD keywords to the company's
interview-prep checklist (reusing `add_checklist_topics`, the same helper
Save Email Context already uses).
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import history  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api import _tasks, app  # noqa: E402


class TestHistorySchemaMigration:
    """history.py's own DB layer, in isolation — no FastAPI involved."""

    def test_fresh_db_has_jd_text_column(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "fresh.db"))
        history.init_db("resume-1")
        conn = sqlite3.connect(history.DB_PATH)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(resume_history)")}
        conn.close()
        assert "jd_text" in cols

    def test_pre_existing_db_without_jd_text_gets_migrated(self, tmp_path, monkeypatch) -> None:
        db_path = tmp_path / "old.db"
        monkeypatch.setattr(history, "DB_PATH", str(db_path))
        # Simulate a database created before this column existed.
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE resume_history ("
            "id TEXT PRIMARY KEY, resume_id TEXT, company_name TEXT NOT NULL, "
            "job_title TEXT, job_url TEXT, pdf_path TEXT NOT NULL, ats_score REAL, "
            "verdict TEXT, applied_date TEXT, created_at REAL NOT NULL)"
        )
        conn.commit()
        conn.close()

        history.init_db("resume-1")

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(resume_history)")}
        conn.close()
        assert "jd_text" in cols

    def test_save_entry_round_trips_jd_text(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "rt.db"))
        history.init_db("resume-1")
        entry = history.save_entry(
            resume_id="resume-1",
            company_name="Acme Corp",
            job_title="AI Engineer",
            job_url="https://example.com/job",
            jd_text="We need a Python engineer with LangChain experience.",
            pdf_path=str(tmp_path / "resume.pdf"),
            ats_score=90.0,
            verdict="Ready to submit",
            applied_date="",
        )
        assert entry["jd_text"] == "We need a Python engineer with LangChain experience."
        fetched = history.get_entry(entry["id"])
        assert fetched is not None
        assert fetched["jd_text"] == "We need a Python engineer with LangChain experience."


def _seed_done_task(task_id: str, *, recruiter_result: dict | None) -> None:
    """Insert a minimal completed-task record matching what `_pipeline`
    leaves behind, including a compiled PDF path (required by save_history)."""
    _tasks[task_id] = {
        "status": "done",
        "resume_id": "fake-resume-id",
        "pdf_path": "/fake/path/resume.pdf",
        "score": 88.5,
        "verdict": "Ready to submit",
        "recruiter_result": recruiter_result,
    }


class TestSaveHistoryEndpoint:
    """POST /api/history — the Generator tab's Save action."""

    def test_unknown_task_returns_400(self) -> None:
        with TestClient(app) as client:
            resp = client.post(
                "/api/history",
                json={"task_id": "does-not-exist", "company_name": "Acme"},
            )
        assert resp.status_code == 400

    def test_saves_entry_and_adds_checklist_topics_from_recruiter_result(
        self, monkeypatch
    ) -> None:
        _seed_done_task(
            "hist-1",
            recruiter_result={
                "job_title": "AI Engineer",
                "required_keywords": ["Python", "LangChain"],
                "preferred_keywords": ["Docker"],
            },
        )

        saved_calls = []

        def fake_history_save(**kwargs):
            saved_calls.append(kwargs)
            return {"id": "entry-1", **kwargs}

        checklist_calls = []

        def fake_add_checklist_topics(resume_id, company, keywords):
            checklist_calls.append((resume_id, company, keywords))
            return keywords  # pretend all were new

        monkeypatch.setattr("src.api.history_save", fake_history_save)
        monkeypatch.setattr("src.api.add_checklist_topics", fake_add_checklist_topics)
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", "/fake/base.tex")
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/history",
                json={
                    "task_id": "hist-1",
                    "company_name": "Acme Corp",
                    "job_url": "https://example.com/job",
                    "jd": "Looking for a Python + LangChain engineer.",
                },
            )

        assert resp.status_code == 200
        body = resp.json()

        # jd_text was passed through to history_save
        assert saved_calls[0]["jd_text"] == "Looking for a Python + LangChain engineer."
        assert saved_calls[0]["company_name"] == "Acme Corp"

        # checklist got the merged required + preferred keywords
        assert checklist_calls[0][1] == "Acme Corp"
        assert set(checklist_calls[0][2]) == {"Python", "LangChain", "Docker"}
        assert set(body["topics_added"]) == {"Python", "LangChain", "Docker"}

    def test_no_keywords_skips_checklist_without_failing(self, monkeypatch) -> None:
        # A real completed task always has a recruiter_result dict (_pipeline
        # sets it before marking status="done") — the realistic "nothing to
        # add" case is an empty keyword list, not a missing/None result.
        _seed_done_task(
            "hist-2",
            recruiter_result={"job_title": "X", "required_keywords": [], "preferred_keywords": []},
        )

        monkeypatch.setattr(
            "src.api.history_save", lambda **kwargs: {"id": "entry-2", **kwargs}
        )
        checklist_called = []
        monkeypatch.setattr(
            "src.api.add_checklist_topics",
            lambda *a, **k: checklist_called.append(1) or [],
        )
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", "/fake/base.tex")
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-2", "company_name": "Acme Corp"}
            )

        assert resp.status_code == 200
        assert resp.json()["topics_added"] == []
        assert not checklist_called

    def test_checklist_failure_is_non_fatal(self, monkeypatch) -> None:
        """The history entry must still save even if the interview-prep
        checklist update blows up — matches Save Email Context's non-fatal
        try/except around the same helper."""
        _seed_done_task(
            "hist-3",
            recruiter_result={
                "job_title": "AI Engineer",
                "required_keywords": ["Python"],
                "preferred_keywords": [],
            },
        )

        monkeypatch.setattr(
            "src.api.history_save", lambda **kwargs: {"id": "entry-3", **kwargs}
        )

        def boom(*a, **k):
            raise RuntimeError("checklist db is on fire")

        monkeypatch.setattr("src.api.add_checklist_topics", boom)
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", "/fake/base.tex")
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/history", json={"task_id": "hist-3", "company_name": "Acme Corp"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["entry"]["id"] == "entry-3"
        assert body["topics_added"] == []
