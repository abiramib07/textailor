"""Tests for `GET /api/compare/{task_id}` — Resume Diff Viewer (base vs.
tailored text). Exercised through FastAPI's TestClient against the real
`app` object. No real Claude CLI call is made.
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


class TestCompareEndpoint:
    """GET /api/compare/{task_id}"""

    def test_unknown_task_returns_400(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/compare/does-not-exist")
        assert resp.status_code == 400

    def test_returns_stripped_text_for_base_and_tailored(self, tmp_path, monkeypatch) -> None:
        # Needs a real \section{} wrapper — the endpoint goes through
        # parse_resume()["plain_text"], not a bare strip_latex() on the raw
        # file, so extract_sections() must actually find something.
        base_tex = tmp_path / "base.tex"
        base_tex.write_text(
            r"\begin{document}\section{Experience}\bulletitem{Built things with Python.}\end{document}",
            encoding="utf-8",
        )
        tailored_tex = tmp_path / "tailored.tex"
        tailored_tex.write_text(
            r"\begin{document}\section{Experience}\bulletitem{Built things with Python and FastAPI.}\end{document}",
            encoding="utf-8",
        )

        _seed_done_task("cmp-1", tex_path=str(tailored_tex))
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", str(base_tex))
        )

        with TestClient(app) as client:
            resp = client.get("/api/compare/cmp-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "Built things with Python." in body["original"]
        assert "Built things with Python and FastAPI." in body["tailored"]
        assert "FastAPI" not in body["original"]

    def test_falls_back_to_base_when_task_has_no_tailored_output_yet(
        self, tmp_path, monkeypatch
    ) -> None:
        base_tex = tmp_path / "base.tex"
        base_tex.write_text(
            r"\begin{document}\section{Experience}\bulletitem{Only the base version exists.}\end{document}",
            encoding="utf-8",
        )
        _seed_done_task("cmp-2", tex_path=None)
        monkeypatch.setattr(
            "src.api._resolve_resume", lambda resume_id: ("fake-resume-id", str(base_tex))
        )

        with TestClient(app) as client:
            resp = client.get("/api/compare/cmp-2")

        assert resp.status_code == 200
        body = resp.json()
        assert body["original"] == body["tailored"]

    def test_missing_file_on_disk_returns_404(self, tmp_path, monkeypatch) -> None:
        _seed_done_task("cmp-3", tex_path=str(tmp_path / "does-not-exist.tex"))
        monkeypatch.setattr(
            "src.api._resolve_resume",
            lambda resume_id: ("fake-resume-id", str(tmp_path / "also-missing.tex")),
        )

        with TestClient(app) as client:
            resp = client.get("/api/compare/cmp-3")

        assert resp.status_code == 404
