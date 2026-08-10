"""Tests for `POST /api/ats-check` — ATS Score Verifier (independent
rescan). Exercised through FastAPI's TestClient against the real `app`
object. No real Claude CLI call is made — `analyze()` is monkeypatched
everywhere it would otherwise fire, since it's the one non-deterministic,
slow, quota-consuming step in this path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from src.api import _tasks, app  # noqa: E402


def _seed_done_task(task_id: str, *, tex_path: str | None) -> None:
    """Insert a minimal completed-task record into the in-memory task store,
    matching the shape `_pipeline`/`post_boost` leave behind."""
    _tasks[task_id] = {
        "status": "done",
        "resume_id": "fake-resume-id",
        "tex_path": tex_path,
        "recruiter_result": {
            "job_title": "AI Engineer",
            "required_keywords": ["Python", "FastAPI"],
            "preferred_keywords": ["Docker"],
        },
    }


class TestAtsCheckEndpoint:
    """POST /api/ats-check"""

    def test_requires_a_jd(self) -> None:
        with TestClient(app) as client:
            resp = client.post("/api/ats-check", data={"jd": "   "})
        assert resp.status_code == 400

    def test_requires_either_a_file_or_a_task_id(self) -> None:
        with TestClient(app) as client:
            resp = client.post("/api/ats-check", data={"jd": "Looking for a Python engineer"})
        assert resp.status_code == 400

    def test_rejects_an_empty_uploaded_file(self) -> None:
        with TestClient(app) as client:
            resp = client.post(
                "/api/ats-check",
                data={"jd": "Looking for a Python engineer"},
                files={"file": ("resume.txt", b"", "text/plain")},
            )
        assert resp.status_code == 400

    def test_scores_an_uploaded_txt_file_via_a_fresh_analyze_call(self, monkeypatch) -> None:
        calls = []

        def fake_analyze(jd: str, text: str) -> dict:
            calls.append((jd, text))
            return {"job_title": "AI Engineer", "required_keywords": ["Python"], "preferred_keywords": []}

        monkeypatch.setattr("src.api.analyze", fake_analyze)

        with TestClient(app) as client:
            resp = client.post(
                "/api/ats-check",
                data={"jd": "Looking for a Python engineer"},
                files={"file": ("resume.txt", b"I have 5 years of Python experience", "text/plain")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["required_found"] == ["Python"]
        assert body["required_missing"] == []
        assert len(calls) == 1  # a genuinely fresh analyze() call, not a cached result

    def test_scores_a_tex_upload_via_strip_latex(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.api.analyze",
            lambda jd, text: {
                "job_title": "AI Engineer",
                "required_keywords": ["Docker"],
                "preferred_keywords": [],
            },
        )
        with TestClient(app) as client:
            resp = client.post(
                "/api/ats-check",
                data={"jd": "need docker experience"},
                files={
                    "file": (
                        "resume.tex",
                        rb"\bulletitem{Deployed services with Docker.}",
                        "text/plain",
                    )
                },
            )
        assert resp.status_code == 200
        assert resp.json()["required_found"] == ["Docker"]

    def test_falls_back_to_task_id_when_no_file_attached(self, tmp_path, monkeypatch) -> None:
        # Needs a real \section{} wrapper — this path now goes through
        # parse_resume()["plain_text"] (see the matching fix in
        # TestCompareEndpoint), not a bare strip_latex() on the raw file.
        tex_path = tmp_path / "resume.tex"
        tex_path.write_text(
            r"\begin{document}\section{Experience}\bulletitem{Experienced with Docker and Python.}\end{document}",
            encoding="utf-8",
        )
        _seed_done_task("ats-1", tex_path=str(tex_path))

        calls = []

        def fake_analyze(jd: str, text: str) -> dict:
            calls.append((jd, text))
            return {"job_title": "X", "required_keywords": ["Docker"], "preferred_keywords": []}

        monkeypatch.setattr("src.api.analyze", fake_analyze)
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", str(tex_path))
        )

        with TestClient(app) as client:
            resp = client.post("/api/ats-check", data={"jd": "need docker", "task_id": "ats-1"})

        assert resp.status_code == 200
        assert len(calls) == 1
        assert resp.json()["required_found"] == ["Docker"]

    def test_unknown_task_id_with_no_file_returns_400(self) -> None:
        with TestClient(app) as client:
            resp = client.post(
                "/api/ats-check", data={"jd": "need docker", "task_id": "does-not-exist"}
            )
        assert resp.status_code == 400
