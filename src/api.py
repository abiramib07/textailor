import logging
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from agents.ats_scorer import score, write_report
from agents.chat_editor import execute as chat_execute
from agents.chat_editor import plan as chat_plan
from agents.chat_editor import undo as chat_undo
from agents.recruiter import analyze
from agents.rewriter import rewrite
from auth.db import init_db as init_auth_db
from auth.router import router as auth_router
from compiler import compile_tex
from latex_parser import parse_resume, strip_latex
from latex_patcher import patch as patch_tex, write_tailored_tex
from main import load_config

# ── Logging ───────────────────────────────────────────────────────────────────
# Don't call basicConfig here — uvicorn configures the root logger at startup.
# Our named logger inherits uvicorn's handlers automatically.
log = logging.getLogger("textailor")

app = FastAPI(title="TexTailor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,  # required so the auth cookies are sent on cross-origin XHR
)

app.include_router(auth_router)

# task_id -> task state
_tasks: dict = {}

# plan_id -> { summary, message }   (short-lived, in-memory)
_plans: dict = {}

# edit_id -> pdf_path   (chat edits)
_chat_pdfs: dict = {}

STEP_NAMES = [
    "Parse resume",
    "Analyse job description",
    "Rewrite sections",
    "Compile PDF",
    "Score ATS match",
]


def _make_step(name: str) -> dict:
    return {"name": name, "status": "pending", "detail": "", "elapsed": None}


def _start_step(task_id: str, idx: int) -> float:
    step = _tasks[task_id]["steps"][idx]
    step["status"] = "running"
    step["elapsed"] = None
    log.info("[%s/%s] %s — started", idx + 1, len(STEP_NAMES), step["name"])
    return time.perf_counter()


def _done_step(task_id: str, idx: int, t0: float, detail: str = ""):
    step = _tasks[task_id]["steps"][idx]
    elapsed = time.perf_counter() - t0
    step["status"] = "done"
    step["detail"] = detail
    step["elapsed"] = f"{elapsed:.1f}s"
    log.info("[%s/%s] %s — done (%ss)  %s", idx + 1, len(STEP_NAMES), step["name"], f"{elapsed:.1f}", detail)


def _fail_step(task_id: str, idx: int, t0: float, err: str):
    step = _tasks[task_id]["steps"][idx]
    elapsed = time.perf_counter() - t0
    step["status"] = "error"
    step["detail"] = err
    step["elapsed"] = f"{elapsed:.1f}s"
    log.error("[%s/%s] %s — FAILED (%ss): %s", idx + 1, len(STEP_NAMES), step["name"], f"{elapsed:.1f}", err)


# ── Pipeline ──────────────────────────────────────────────────────────────────
def _pipeline(task_id: str, jd: str, config: dict):
    log.info("Pipeline started  task_id=%s", task_id)
    _tasks[task_id]["status"] = "running"
    pipeline_start = time.perf_counter()

    try:
        # Step 1 — Parse
        t = _start_step(task_id, 0)
        resume_data = parse_resume(config["resume_path"])
        sections = list(resume_data["sections"].keys())
        _done_step(task_id, 0, t, f"Sections: {', '.join(sections)}")

        # Step 2 — Recruiter
        t = _start_step(task_id, 1)
        recruiter_result = analyze(jd, resume_data["plain_text"])
        job_title = recruiter_result.get("job_title", "Role")
        missing = len(recruiter_result["missing_from_resume"])
        _done_step(task_id, 1, t, f"Role: {job_title} · {missing} missing keywords")

        # Step 3 — Rewrite
        t = _start_step(task_id, 2)
        sections_to_rewrite = config.get(
            "sections_to_rewrite",
            ["Career Objective", "Experience", "Projects", "Skills"],
        )
        rewritten = rewrite(
            sections=resume_data["sections"],
            priority_keywords=recruiter_result["priority_adds"],
            key_action_verbs=recruiter_result["key_action_verbs"],
            sections_to_rewrite=sections_to_rewrite,
        )
        _done_step(task_id, 2, t, f"Rewritten: {', '.join(rewritten.keys())}")

        # Step 4 — Compile
        t = _start_step(task_id, 3)
        safe_title = re.sub(r"[^\w\-]", "_", job_title)
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_dir = Path(config["output_dir"]) / f"{safe_title}_{date_str}"
        out_dir.mkdir(parents=True, exist_ok=True)
        tex_out = str(out_dir / "resume_tailored.tex")
        write_tailored_tex(
            original_tex=resume_data["raw_tex"],
            rewritten_sections=rewritten,
            original_sections=resume_data["sections"],
            output_path=tex_out,
        )
        pdf_path = compile_tex(tex_out)
        _done_step(task_id, 3, t, f"PDF: {Path(pdf_path).name}")

        # Step 5 — ATS score (score against full patched resume, not just rewritten sections)
        t = _start_step(task_id, 4)
        full_patched_tex = patch_tex(resume_data["raw_tex"], rewritten, resume_data["sections"])
        score_result = score(recruiter_result, strip_latex(full_patched_tex))
        write_report(score_result, str(out_dir / "ats_report.txt"))
        _done_step(task_id, 4, t, f"{score_result['overall_score']}% — {score_result['verdict']}")

        total = time.perf_counter() - pipeline_start
        log.info("Pipeline complete  %.1fs  score=%s%%  %s", total, score_result["overall_score"], score_result["verdict"])

        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["pdf_path"] = pdf_path
        _tasks[task_id]["score"] = score_result["overall_score"]
        _tasks[task_id]["verdict"] = score_result["verdict"]
        _tasks[task_id]["score_result"] = score_result
        _tasks[task_id]["recruiter_result"] = recruiter_result
        _tasks[task_id]["out_dir"] = str(out_dir)

    except Exception as exc:
        # mark the currently-running step as failed
        for i, s in enumerate(_tasks[task_id]["steps"]):
            if s["status"] == "running":
                _fail_step(task_id, i, pipeline_start, str(exc))
                break
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["error"] = str(exc)
        log.error("Pipeline failed: %s", exc, exc_info=True)


# ── Routes ────────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    jd: str


@app.on_event("startup")
def _startup():
    init_auth_db()
    log.info("TexTailor API ready on http://localhost:8000")
    log.info("Docs → http://localhost:8000/docs")


@app.post("/api/generate")
def generate(req: GenerateRequest):
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "pending",
        "steps": [_make_step(n) for n in STEP_NAMES],
        "score": None,
        "verdict": None,
        "pdf_path": None,
        "error": None,
    }
    config = load_config()
    log.info("New request  task_id=%s  jd_length=%d chars", task_id, len(req.jd))
    t = threading.Thread(target=_pipeline, args=(task_id, req.jd, config), daemon=True)
    t.start()
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def get_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "status": task["status"],
        "steps": task["steps"],
        "score": task["score"],
        "verdict": task["verdict"],
        "error": task["error"],
        "has_pdf": task["pdf_path"] is not None and Path(task["pdf_path"]).exists(),
    }


@app.get("/api/pdf/{task_id}")
def get_pdf(task_id: str):
    task = _tasks.get(task_id)
    if not task or not task["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF not ready")
    pdf = Path(task["pdf_path"])
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF file missing")
    return FileResponse(str(pdf), media_type="application/pdf", headers={"Content-Disposition": "inline"})


# ── Chat endpoints ────────────────────────────────────────────────────────────

class ChatPlanRequest(BaseModel):
    message: str


class ChatExecuteRequest(BaseModel):
    plan_id: str
    message: str


@app.post("/api/chat/plan")
def post_chat_plan(req: ChatPlanRequest):
    """Phase 1 — analyse intent, return plain-English plan. No resume changes yet."""
    result = chat_plan(req.message)
    plan_id = str(uuid.uuid4())
    _plans[plan_id] = {"summary": result.get("summary", ""), "message": req.message}
    log.info("Chat plan  plan_id=%s  intent=%s  confidence=%s",
             plan_id, result.get("intent_type"), result.get("confidence"))
    return {**result, "plan_id": plan_id}


@app.post("/api/chat/execute")
def post_chat_execute(req: ChatExecuteRequest):
    """Phase 2 — user confirmed; apply LaTeX patches, compile, serve new PDF."""
    plan_data = _plans.get(req.plan_id)
    if not plan_data:
        raise HTTPException(status_code=404, detail="Plan not found or expired — please resend your request")
    result = chat_execute(message=req.message, plan_summary=plan_data["summary"])
    edit_id = str(uuid.uuid4())
    if result["success"] and result.get("pdf_path"):
        _chat_pdfs[edit_id] = result["pdf_path"]
    log.info("Chat execute  edit_id=%s  success=%s", edit_id, result["success"])
    return {
        "edit_id": edit_id,
        "success": result["success"],
        "done_summary": result.get("done_summary", ""),
        "has_pdf": bool(result.get("pdf_path")),
        "error": result.get("error"),
    }


@app.get("/api/chat/pdf/{edit_id}")
def get_chat_pdf(edit_id: str):
    """Serve the PDF produced by a chat edit."""
    pdf_path = _chat_pdfs.get(edit_id)
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="Chat PDF not available")
    return FileResponse(str(pdf_path), media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.post("/api/chat/undo")
def post_chat_undo():
    """Revert resume/main.tex to the previous backup and recompile."""
    result = chat_undo()
    edit_id = str(uuid.uuid4())
    if result["success"] and result.get("pdf_path"):
        _chat_pdfs[edit_id] = result["pdf_path"]
    return {
        "edit_id": edit_id,
        "success": result["success"],
        "done_summary": result.get("summary", ""),
        "has_pdf": bool(result.get("pdf_path")),
        "error": None if result["success"] else result.get("summary"),
    }


# ── ATS Report endpoint ───────────────────────────────────────────────────────

@app.get("/api/report/{task_id}")
def get_report(task_id: str):
    """Return the full structured ATS score report for a completed task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    score_result = task.get("score_result")
    if not score_result:
        raise HTTPException(status_code=404, detail="Report not ready yet")
    return score_result


# ── ATS Boost endpoint ────────────────────────────────────────────────────────

@app.post("/api/boost/{task_id}")
def post_boost(task_id: str):
    """Re-run the rewriter with ALL missing keywords to push ATS score toward 90%+."""
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    recruiter_result = task.get("recruiter_result")
    score_result = task.get("score_result")
    out_dir_str = task.get("out_dir")

    if not recruiter_result or not score_result or not out_dir_str:
        raise HTTPException(status_code=400, detail="Missing pipeline data — re-generate first")

    config = load_config()
    all_missing = score_result["required_missing"] + score_result["preferred_missing"]
    if not all_missing:
        return {
            "boost_id": None,
            "score": score_result["overall_score"],
            "verdict": score_result["verdict"],
            "has_pdf": False,
            "message": "No missing keywords — score is already optimal.",
        }

    resume_data = parse_resume(config["resume_path"])
    rewritten = rewrite(
        sections=resume_data["sections"],
        priority_keywords=all_missing,
        key_action_verbs=recruiter_result.get("key_action_verbs", []),
        sections_to_rewrite=["Professional Summary", "Experience", "Technical Skills"],
    )

    out_dir = Path(out_dir_str)
    tex_out = str(out_dir / "resume_boosted.tex")
    write_tailored_tex(
        original_tex=resume_data["raw_tex"],
        rewritten_sections=rewritten,
        original_sections=resume_data["sections"],
        output_path=tex_out,
    )
    pdf_path = compile_tex(tex_out)

    full_patched_tex = patch_tex(resume_data["raw_tex"], rewritten, resume_data["sections"])
    new_score = score(recruiter_result, strip_latex(full_patched_tex))
    write_report(new_score, str(out_dir / "ats_report_boosted.txt"))

    task["score_result"] = new_score
    task["score"] = new_score["overall_score"]
    task["verdict"] = new_score["verdict"]
    task["pdf_path"] = pdf_path

    boost_id = str(uuid.uuid4())
    _chat_pdfs[boost_id] = pdf_path
    log.info("Boost complete  score=%s%%  boost_id=%s", new_score["overall_score"], boost_id)

    return {
        "boost_id": boost_id,
        "score": new_score["overall_score"],
        "verdict": new_score["verdict"],
        "has_pdf": True,
    }


# ── Resume MD editor endpoints ────────────────────────────────────────────────

_RESUME_MD = Path(__file__).parent.parent / "resume" / "resume-content.md"
_RESUME_TEX_PATH = Path(__file__).parent.parent / "resume" / "main.tex"


@app.get("/api/resume-md")
def get_resume_md():
    """Return the resume content as Markdown. Generates it from main.tex on first call."""
    if not _RESUME_MD.exists():
        from md_converter import tex_to_md
        tex = _RESUME_TEX_PATH.read_text(encoding="utf-8")
        md = tex_to_md(tex)
        _RESUME_MD.write_text(md, encoding="utf-8")
    return {"content": _RESUME_MD.read_text(encoding="utf-8")}


class ResumeMdBody(BaseModel):
    content: str


@app.put("/api/resume-md")
def put_resume_md(req: ResumeMdBody):
    """Save the edited Markdown draft to resume/resume-content.md."""
    _RESUME_MD.write_text(req.content, encoding="utf-8")
    return {"saved": True}


@app.post("/api/resume-md/sync")
def sync_resume_md():
    """Convert the saved Markdown draft → LaTeX, update main.tex, compile PDF."""
    if not _RESUME_MD.exists():
        raise HTTPException(status_code=400, detail="No resume draft found — open the editor first")

    from md_converter import md_to_tex
    import shutil as _shutil
    from agents.chat_editor import _next_backup_path

    md = _RESUME_MD.read_text(encoding="utf-8")
    original_tex = _RESUME_TEX_PATH.read_text(encoding="utf-8")

    new_tex = md_to_tex(md, original_tex)

    backup = _next_backup_path()
    _shutil.copy2(_RESUME_TEX_PATH, backup)
    _RESUME_TEX_PATH.write_text(new_tex, encoding="utf-8")

    try:
        pdf_path = compile_tex(str(_RESUME_TEX_PATH))
    except Exception as exc:
        _shutil.copy2(backup, _RESUME_TEX_PATH)
        raise HTTPException(status_code=500, detail=f"Compile failed — reverted. {exc}")

    edit_id = str(uuid.uuid4())
    _chat_pdfs[edit_id] = pdf_path
    log.info("Resume MD synced  edit_id=%s  pdf=%s", edit_id, pdf_path)
    return {"synced": True, "edit_id": edit_id, "has_pdf": True}


@app.get("/api/template")
def get_template():
    config = load_config()
    tex = Path(config["resume_path"])
    pdf = tex.with_suffix(".pdf")
    # Recompile if PDF is missing or main.tex has been updated since last compile
    if not pdf.exists() or tex.stat().st_mtime > pdf.stat().st_mtime:
        try:
            compile_tex(str(tex))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Template compile failed: {exc}")
    if not pdf.exists():
        raise HTTPException(status_code=500, detail="Template PDF could not be produced")
    return FileResponse(str(pdf), media_type="application/pdf", headers={"Content-Disposition": "inline"})
