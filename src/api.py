"""FastAPI application: the resume-tailoring pipeline (generate/status/pdf),
chat-based editing, resume history, the ATS verifier, and the email
generator, plus the mounted `auth` router. This is the HTTP counterpart to
`main.py`'s file-watcher CLI — same pipeline, exposed over REST for the
Angular frontend.
"""

import logging
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from agents.ats_scorer import score, write_report
from agents.chat_editor import execute as chat_execute
from agents.chat_editor import plan as chat_plan
from agents.chat_editor import undo as chat_undo
from agents.email_generator import generate_email, revise_email
from agents.email_sender import send_email
from agents.pitch_generator import generate_pitches
from agents.recruiter import analyze
from agents.resume_importer import extract_text
from agents.rewriter import rewrite
from agents.verifier import explain_keyword, verify
from auth.db import init_db as init_auth_db
from auth.router import router as auth_router
from career.db import init_db as init_career_db
from career.email_link import save_email_context
from career.router import router as career_router
from career.topic_mapping import log_keywords as log_jd_keywords
from compiler import compile_tex
from email_patterns import init_db as init_email_patterns_db
from email_patterns import learn as learn_email_pattern
from email_patterns import recent_patterns as recent_email_patterns
from history import get_entry as history_get
from history import init_db as init_history_db
from history import list_entries as history_list
from history import save_entry as history_save
from latex_parser import parse_resume, strip_latex
from latex_patcher import add_skills_row, write_tailored_tex
from latex_patcher import patch as patch_tex
from main import load_config
from notifier import notify_email_done, notify_resume_done, notify_resume_failed
from resumes.db import get_default_resume, get_resume, resolve_resume_id
from resumes.db import init_db as init_resumes_db
from resumes.router import router as resumes_router

# ── Logging ───────────────────────────────────────────────────────────────────
# uvicorn's --log-level only configures its OWN loggers ("uvicorn",
# "uvicorn.error", "uvicorn.access"), not the root logger — a bare
# getLogger("textailor") with no handler of its own silently drops every
# record (Python's root logger defaults to WARNING with no handler). Attach
# our own handler so INFO-level execution trace actually reaches the console
# regardless of how uvicorn was started.
log = logging.getLogger("textailor")
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%H:%M:%S")
    )
    log.addHandler(_handler)
    log.propagate = False

app = FastAPI(title="TexTailor API")

app.add_middleware(
    CORSMiddleware,
    # Matches any localhost/127.0.0.1 port, not just 4200 — `ng serve` picks a
    # different port if 4200 is busy, and IDE preview/port-forwarding proxies
    # (VS Code, Cursor, etc.) often serve the app through their own random
    # port too. Still safe for a local-only dev tool since it never matches
    # a non-loopback origin.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,  # required so the auth cookies are sent on cross-origin XHR
)

app.include_router(auth_router)
app.include_router(career_router)
app.include_router(resumes_router)

# task_id -> task state
_tasks: dict = {}

# plan_id -> { summary, message, resume_path, resume_id }   (short-lived, in-memory)
_plans: dict = {}

# resume_id -> [{role, text}, ...]   (chat plan-phase transcript, cleared once
# a plan for that resume is successfully applied)
_chat_history: dict[str, list[dict]] = {}

# edit_id -> pdf_path   (chat edits)
_chat_pdfs: dict = {}

# email_id -> { to, subject, body, role_title, history: [...] }
_emails: dict = {}

STEP_NAMES = [
    "Parse resume",
    "Analyse job description",
    "Rewrite sections",
    "Compile PDF",
    "Score ATS match",
]


def _resolve_resume(resume_id: str | None) -> tuple[str, str]:
    """Return (resume_id, tex_path) for a request — falls back to the
    default resume identity when `resume_id` is None."""
    rid = resolve_resume_id(resume_id)
    resume = get_resume(rid)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return rid, resume["tex_path"]


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
    log.info(
        "[%s/%s] %s — done (%ss)  %s",
        idx + 1,
        len(STEP_NAMES),
        step["name"],
        f"{elapsed:.1f}",
        detail,
    )


def _fail_step(task_id: str, idx: int, t0: float, err: str):
    step = _tasks[task_id]["steps"][idx]
    elapsed = time.perf_counter() - t0
    step["status"] = "error"
    step["detail"] = err
    step["elapsed"] = f"{elapsed:.1f}s"
    log.error(
        "[%s/%s] %s — FAILED (%ss): %s",
        idx + 1,
        len(STEP_NAMES),
        step["name"],
        f"{elapsed:.1f}",
        err,
    )


# ── Pipeline ──────────────────────────────────────────────────────────────────
def _pipeline(task_id: str, jd: str, config: dict, resume_path: str, resume_id: str):
    log.info("Pipeline started  task_id=%s  resume_id=%s", task_id, resume_id)
    _tasks[task_id]["status"] = "running"
    pipeline_start = time.perf_counter()

    try:
        # Step 1 — Parse
        t = _start_step(task_id, 0)
        resume_data = parse_resume(resume_path)
        sections = list(resume_data["sections"].keys())
        _done_step(task_id, 0, t, f"Sections: {', '.join(sections)}")

        # Step 2 — Recruiter
        t = _start_step(task_id, 1)
        recruiter_result = analyze(jd, resume_data["plain_text"])
        job_title = recruiter_result.get("job_title", "Role")
        _tasks[task_id]["job_title"] = job_title
        missing = len(recruiter_result["missing_from_resume"])
        _done_step(task_id, 1, t, f"Role: {job_title} · {missing} missing keywords")
        try:
            log_jd_keywords(None, recruiter_result, jd, resume_id)
        except Exception:
            log.exception("Topic-mapping keyword logging failed (non-fatal)")

        # Step 3 — Rewrite
        t = _start_step(task_id, 2)
        sections_to_rewrite = config.get(
            "sections_to_rewrite",
            ["Career Objective", "Experience", "Projects", "Skills"],
        )
        rewritten, rewrite_warnings = rewrite(
            sections=resume_data["sections"],
            priority_keywords=recruiter_result["priority_adds"],
            key_action_verbs=recruiter_result["key_action_verbs"],
            sections_to_rewrite=sections_to_rewrite,
        )
        _tasks[task_id]["warnings"] = rewrite_warnings
        detail = f"Rewritten: {', '.join(rewritten.keys())}"
        if rewrite_warnings:
            detail += f" — ⚠ {len(rewrite_warnings)} section(s) kept unchanged, see warnings"
        _done_step(task_id, 2, t, detail)

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
        log.info(
            "Pipeline complete  %.1fs  score=%s%%  %s",
            total,
            score_result["overall_score"],
            score_result["verdict"],
        )

        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["pdf_path"] = pdf_path
        _tasks[task_id]["tex_path"] = tex_out
        _tasks[task_id]["score"] = score_result["overall_score"]
        _tasks[task_id]["verdict"] = score_result["verdict"]
        _tasks[task_id]["score_result"] = score_result
        _tasks[task_id]["recruiter_result"] = recruiter_result
        _tasks[task_id]["out_dir"] = str(out_dir)
        notify_resume_done(job_title, score_result["overall_score"], score_result["verdict"])

    except Exception as exc:
        # mark the currently-running step as failed
        for i, s in enumerate(_tasks[task_id]["steps"]):
            if s["status"] == "running":
                _fail_step(task_id, i, pipeline_start, str(exc))
                break
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["error"] = str(exc)
        log.error("Pipeline failed: %s", exc, exc_info=True)
        notify_resume_failed(_tasks[task_id].get("job_title", "Resume"), str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    """Body for POST /api/generate."""

    jd: str
    resume_id: str | None = None


@app.on_event("startup")
def _startup() -> None:
    """Initialize the auth, resumes, history, email-pattern, and career
    databases on startup, in dependency order (resumes must exist before
    the other tables can backfill their `resume_id` column)."""
    config = load_config()
    init_auth_db()
    init_resumes_db(config["resume_path"])
    default_resume_id = get_default_resume()["id"]
    init_history_db(default_resume_id)
    init_email_patterns_db(default_resume_id)
    init_career_db(default_resume_id)
    log.info("TexTailor API ready on http://localhost:8000")
    log.info("Docs → http://localhost:8000/docs")


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    """Start the tailoring pipeline in a background thread; returns a task_id
    to poll via /api/status/{task_id}."""
    task_id = str(uuid.uuid4())
    resume_id, resume_path = _resolve_resume(req.resume_id)
    _tasks[task_id] = {
        "status": "pending",
        "steps": [_make_step(n) for n in STEP_NAMES],
        "score": None,
        "verdict": None,
        "pdf_path": None,
        "error": None,
        "resume_id": resume_id,
        "warnings": [],
    }
    config = load_config()
    log.info("New request  task_id=%s  jd_length=%d chars", task_id, len(req.jd))
    t = threading.Thread(
        target=_pipeline, args=(task_id, req.jd, config, resume_path, resume_id), daemon=True
    )
    t.start()
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def get_status(task_id: str) -> dict:
    """Poll a task's pipeline progress (steps, score, verdict, error)."""
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
        "warnings": task.get("warnings", []),
    }


@app.get("/api/pdf/{task_id}")
def get_pdf(task_id: str) -> FileResponse:
    """Serve the tailored resume PDF for a completed task."""
    task = _tasks.get(task_id)
    if not task or not task["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF not ready")
    pdf = Path(task["pdf_path"])
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF file missing")
    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


# ── Chat endpoints ────────────────────────────────────────────────────────────


class ChatPlanRequest(BaseModel):
    """Body for POST /api/chat/plan."""

    message: str
    resume_id: str | None = None


class ChatExecuteRequest(BaseModel):
    """Body for POST /api/chat/execute."""

    plan_id: str
    message: str


@app.post("/api/chat/plan")
def post_chat_plan(req: ChatPlanRequest):
    """Phase 1 — analyse intent, return plain-English plan. No resume changes yet.

    Replays this resume's running chat history back to the plan agent so
    follow-up messages ("add the above", answering a clarifying question)
    can be resolved instead of analysed as a standalone request.
    """
    resume_id, resume_path = _resolve_resume(req.resume_id)
    history = _chat_history.setdefault(resume_id, [])
    result = chat_plan(req.message, Path(resume_path), history)
    plan_id = str(uuid.uuid4())
    _plans[plan_id] = {
        "summary": result.get("summary", ""),
        "message": req.message,
        "resume_path": resume_path,
        "resume_id": resume_id,
    }

    history.append({"role": "user", "text": req.message})
    assistant_text = result.get("summary", "")
    if result.get("questions"):
        assistant_text += " " + " ".join(result["questions"])
    history.append({"role": "assistant", "text": assistant_text})

    log.info(
        "Chat plan  plan_id=%s  resume_id=%s  intent=%s  confidence=%s",
        plan_id,
        resume_id,
        result.get("intent_type"),
        result.get("confidence"),
    )
    return {**result, "plan_id": plan_id}


@app.post("/api/chat/execute")
def post_chat_execute(req: ChatExecuteRequest):
    """Phase 2 — user confirmed; apply LaTeX patches, compile, serve new PDF.

    On success, clears the resume's chat history — the accumulated context
    has now been resolved and applied, so the next message starts fresh.
    """
    plan_data = _plans.get(req.plan_id)
    if not plan_data:
        raise HTTPException(
            status_code=404, detail="Plan not found or expired — please resend your request"
        )
    result = chat_execute(
        message=req.message,
        plan_summary=plan_data["summary"],
        resume_path=Path(plan_data["resume_path"]),
    )
    edit_id = str(uuid.uuid4())
    if result["success"] and result.get("pdf_path"):
        _chat_pdfs[edit_id] = result["pdf_path"]

    resume_id = plan_data.get("resume_id")
    if resume_id:
        if result["success"]:
            _chat_history[resume_id] = []
        else:
            history = _chat_history.setdefault(resume_id, [])
            history.append(
                {
                    "role": "assistant",
                    "text": f"(Tried to apply that and it failed: {result.get('error', 'unknown error')})",
                }
            )

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
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


class ChatUndoRequest(BaseModel):
    """Body for POST /api/chat/undo."""

    resume_id: str | None = None


@app.post("/api/chat/undo")
def post_chat_undo(req: ChatUndoRequest | None = None):
    """Revert a resume's `.tex` file to the previous backup and recompile."""
    _, resume_path = _resolve_resume(req.resume_id if req else None)
    result = chat_undo(Path(resume_path))
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


class BoostRequest(BaseModel):
    """Body for POST /api/boost/{task_id}."""

    selected_keywords: list[str] | None = None


@app.post("/api/boost/{task_id}")
def post_boost(task_id: str, req: BoostRequest | None = None):
    """Re-run the rewriter to push the ATS score up.

    Only weaves in `req.selected_keywords` if given (the user picked which
    missing keywords they actually have) — otherwise falls back to every
    missing keyword, for backward compatibility with a direct boost call.
    """
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    recruiter_result = task.get("recruiter_result")
    score_result = task.get("score_result")
    out_dir_str = task.get("out_dir")

    if not recruiter_result or not score_result or not out_dir_str:
        raise HTTPException(status_code=400, detail="Missing pipeline data — re-generate first")

    # Build on top of whatever's already tailored for THIS task, not the
    # pristine base resume — otherwise each Weave-in click re-tailors from
    # scratch with only the newly selected keywords, throwing away every
    # keyword the initial /api/generate pass (or an earlier Weave-in click on
    # this same task) already wove in. Read the path from the task's own
    # state (set by the pipeline / a prior boost below) rather than checking
    # which files exist in `out_dir` — that directory is keyed only by job
    # title + date, so two tasks generated the same day for the same role
    # share it, and a directory-existence check would silently pick up a
    # stale `resume_boosted.tex` left over from a *different* task.
    out_dir = Path(out_dir_str)
    resume_path = task.get("tex_path")
    if not resume_path:
        _, resume_path = _resolve_resume(task.get("resume_id"))

    all_missing = score_result["required_missing"] + score_result["preferred_missing"]
    selected = req.selected_keywords if req and req.selected_keywords is not None else all_missing
    # Keep only keywords that are actually missing — ignore anything stale/unexpected.
    selected = [kw for kw in selected if kw in all_missing]

    if not selected:
        return {
            "boost_id": None,
            "score": score_result["overall_score"],
            "verdict": score_result["verdict"],
            "has_pdf": False,
            "message": "No keywords selected — nothing to weave in.",
            "warnings": [],
        }

    log.info(
        "Weave-in START  task=%s  keywords=%d  before_score=%s%%  selected=%s",
        task_id,
        len(selected),
        score_result["overall_score"],
        selected,
    )
    t_start = time.monotonic()

    try:
        resume_data = parse_resume(resume_path)
        # Technical Skills is a structured `\skillrow` table, not prose — let
        # the AI rewrite only the narrative sections (where "weave in
        # naturally" actually means something) and add the keywords to the
        # skills table the same deterministic, non-destructive way "Add to
        # Skills" does. An earlier version let the AI rewrite Technical
        # Skills too, and it would drop unrelated existing skills (AWS,
        # MLOps, etc.) while restructuring the table to fit the new ones in.
        rewritten, rewrite_warnings = rewrite(
            sections=resume_data["sections"],
            priority_keywords=selected,
            key_action_verbs=recruiter_result.get("key_action_verbs", []),
            sections_to_rewrite=["Professional Summary", "Experience"],
        )
        if "Technical Skills" in resume_data["sections"]:
            rewritten["Technical Skills"] = add_skills_row(
                resume_data["sections"]["Technical Skills"], selected
            )

        tex_out = str(out_dir / "resume_boosted.tex")
        write_tailored_tex(
            original_tex=resume_data["raw_tex"],
            rewritten_sections=rewritten,
            original_sections=resume_data["sections"],
            output_path=tex_out,
        )
        log.info("Weave-in: compiling %s", tex_out)
        pdf_path = compile_tex(tex_out)
    except Exception as exc:
        log.exception("Weave-in FAILED  task=%s  after %.1fs", task_id, time.monotonic() - t_start)
        raise HTTPException(status_code=500, detail=f"Weave-in failed: {exc}") from exc

    full_patched_tex = patch_tex(resume_data["raw_tex"], rewritten, resume_data["sections"])
    new_score = score(recruiter_result, strip_latex(full_patched_tex))
    write_report(new_score, str(out_dir / "ats_report_boosted.txt"))

    task["warnings"] = rewrite_warnings
    task["score_result"] = new_score
    task["score"] = new_score["overall_score"]
    task["verdict"] = new_score["verdict"]
    task["pdf_path"] = pdf_path
    task["tex_path"] = tex_out

    boost_id = str(uuid.uuid4())
    _chat_pdfs[boost_id] = pdf_path

    before_score = score_result["overall_score"]
    after_score = new_score["overall_score"]
    log.info(
        "Weave-in DONE  task=%s  boost_id=%s  score %.1f%% -> %.1f%%  elapsed=%.1fs",
        task_id,
        boost_id,
        before_score,
        after_score,
        time.monotonic() - t_start,
    )
    if after_score < before_score:
        newly_missing = sorted(
            set(new_score["required_missing"] + new_score["preferred_missing"]) - set(all_missing)
        )
        log.warning(
            "Weave-in REGRESSED score for task=%s (%.1f%% -> %.1f%%) — "
            "keywords now missing that were previously found: %s",
            task_id,
            before_score,
            after_score,
            newly_missing,
        )

    return {
        "boost_id": boost_id,
        "score": new_score["overall_score"],
        "verdict": new_score["verdict"],
        "has_pdf": True,
        "warnings": rewrite_warnings,
    }


class AddSkillsRequest(BaseModel):
    """Body for POST /api/boost/add-skills/{task_id}."""

    selected_keywords: list[str]


@app.post("/api/boost/add-skills/{task_id}")
def post_add_skills(task_id: str, req: AddSkillsRequest):
    """Directly add selected missing keywords into the Technical Skills
    table, grouped under the most relevant existing or new category row.

    A fast, deterministic alternative to the full AI-rewrite boost: no LLM
    call, so it can't misattribute a skill — it only adds exactly what the
    user checked off.
    """
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    recruiter_result = task.get("recruiter_result")
    score_result = task.get("score_result")
    out_dir_str = task.get("out_dir")
    if not recruiter_result or not score_result or not out_dir_str:
        raise HTTPException(status_code=400, detail="Missing pipeline data — re-generate first")

    all_missing = score_result["required_missing"] + score_result["preferred_missing"]
    selected = [kw for kw in req.selected_keywords if kw in all_missing]
    if not selected:
        return {
            "boost_id": None,
            "score": score_result["overall_score"],
            "verdict": score_result["verdict"],
            "has_pdf": False,
            "added": [],
            "message": "No keywords selected — nothing added.",
            "warnings": [],
        }

    # Build on top of whatever's already tailored for this task (see the
    # matching comment in post_boost above) rather than the pristine base
    # resume, so this doesn't throw away keywords the initial /api/generate
    # pass — or an earlier Weave-in/Add-to-Skills click on this same task —
    # already added.
    resume_path = task.get("tex_path")
    if not resume_path:
        _, resume_path = _resolve_resume(task.get("resume_id"))

    log.info(
        "Add-to-Skills START  task=%s  keywords=%d  before_score=%s%%  selected=%s",
        task_id,
        len(selected),
        score_result["overall_score"],
        selected,
    )
    t_start = time.monotonic()

    try:
        resume_data = parse_resume(resume_path)
        skills_section = resume_data["sections"].get("Technical Skills", "")
        if not skills_section:
            raise HTTPException(
                status_code=400, detail="No Technical Skills section found to add to"
            )

        rewritten = {"Technical Skills": add_skills_row(skills_section, selected)}

        out_dir = Path(out_dir_str)
        tex_out = str(out_dir / "resume_skills_added.tex")
        write_tailored_tex(
            original_tex=resume_data["raw_tex"],
            rewritten_sections=rewritten,
            original_sections=resume_data["sections"],
            output_path=tex_out,
        )
        pdf_path = compile_tex(tex_out)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception(
            "Add-to-Skills FAILED  task=%s  after %.1fs", task_id, time.monotonic() - t_start
        )
        raise HTTPException(status_code=500, detail=f"Add-to-Skills failed: {exc}") from exc

    full_patched_tex = patch_tex(resume_data["raw_tex"], rewritten, resume_data["sections"])
    new_score = score(recruiter_result, strip_latex(full_patched_tex))
    write_report(new_score, str(out_dir / "ats_report_skills_added.txt"))

    task["score_result"] = new_score
    task["score"] = new_score["overall_score"]
    task["verdict"] = new_score["verdict"]
    task["pdf_path"] = pdf_path
    task["tex_path"] = tex_out

    boost_id = str(uuid.uuid4())
    _chat_pdfs[boost_id] = pdf_path
    log.info(
        "Add-to-Skills DONE  task=%s  boost_id=%s  score %.1f%% -> %.1f%%  elapsed=%.1fs",
        task_id,
        boost_id,
        score_result["overall_score"],
        new_score["overall_score"],
        time.monotonic() - t_start,
    )

    return {
        "boost_id": boost_id,
        "score": new_score["overall_score"],
        "verdict": new_score["verdict"],
        "has_pdf": True,
        "added": selected,
        "warnings": [],
    }


@app.post("/api/rescore/{task_id}")
def post_rescore(task_id: str):
    """Recompute the ATS score from whatever is currently on disk for this
    task's resume identity — used after a chat edit (which patches the
    resume file directly, outside the pipeline) to see its effect on the
    score without re-running the whole generation."""
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    recruiter_result = task.get("recruiter_result")
    if not recruiter_result:
        raise HTTPException(status_code=400, detail="Missing pipeline data — re-generate first")

    _, resume_path = _resolve_resume(task.get("resume_id"))
    resume_data = parse_resume(resume_path)
    new_score = score(recruiter_result, resume_data["plain_text"])

    task["score_result"] = new_score
    task["score"] = new_score["overall_score"]
    task["verdict"] = new_score["verdict"]
    log.info("Rescore complete  task_id=%s  score=%s%%", task_id, new_score["overall_score"])

    return new_score


@app.get("/api/compare/{task_id}")
def get_compare(task_id: str) -> dict:
    """Return plain-text versions of this task's pristine base resume and its
    current tailored output, for a side-by-side diff — "before" is the
    resume identity's untouched `.tex`, "after" is whatever this task's
    latest Weave-in/Add-to-Skills pass left in `task["tex_path"]` (falling
    back to the base resume if the task hasn't tailored anything yet)."""
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    _, base_path = _resolve_resume(task.get("resume_id"))
    tailored_path = task.get("tex_path") or base_path

    # `parse_resume()["plain_text"]` (not a raw read + strip_latex on the
    # whole file) — the raw file also contains the preamble (documentclass
    # options, package configs, \newcommand macro definitions), which is
    # LaTeX noise a diff reader has no use for. parse_resume() already
    # isolates just the document's sections before stripping.
    try:
        original_text = parse_resume(base_path)["plain_text"]
        tailored_text = parse_resume(tailored_path)["plain_text"]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Resume file missing on disk: {exc}") from exc

    return {
        "original": original_text,
        "tailored": tailored_text,
    }


class PitchRequest(BaseModel):
    """Body for POST /api/pitch/{task_id}."""

    jd: str


@app.post("/api/pitch/{task_id}")
def post_pitch(task_id: str, req: PitchRequest) -> dict:
    """Draft a fresh short pitch / written bio / project talking points /
    cover letter template from this task's job description and its current
    tailored resume. Preview only — nothing is persisted here; the frontend
    saves each field via PUT /api/career/personal-info once the user
    approves, so a regenerate never silently overwrites a hand-edited value."""
    if not req.jd.strip():
        raise HTTPException(status_code=400, detail="Missing job description")

    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    _, base_path = _resolve_resume(task.get("resume_id"))
    tailored_path = task.get("tex_path") or base_path
    try:
        resume_text = parse_resume(tailored_path)["plain_text"]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Resume file missing on disk: {exc}") from exc

    try:
        result = generate_pitches(req.jd, resume_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pitch generation failed: {exc}") from exc

    log.info("Pitch generated  task_id=%s", task_id)
    return result


# ── ATS Score Verifier — independent resume+JD rescan ───────────────────────────


@app.post("/api/ats-check")
async def post_ats_check(
    jd: str = Form(...),
    task_id: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    """Independently verify an ATS score: re-run recruiter keyword analysis
    AND scoring from scratch against fresh resume text — either a freshly
    uploaded file, or (if none is attached) the given task's current tex,
    still read fresh off disk and re-analyzed rather than reusing the
    task's cached `recruiter_result`. This catches drift in the keyword
    extraction itself, not just re-scoring against a stale list. Fully
    decoupled from pipeline state — nothing is persisted."""
    if not jd.strip():
        raise HTTPException(status_code=400, detail="Paste the job description first")

    if file is not None and file.filename:
        filename = file.filename
        ext = Path(filename).suffix.lower()
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        if ext == ".tex":
            resume_text = strip_latex(data.decode("utf-8"))
        else:
            try:
                raw_text = extract_text(data, filename)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if not raw_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="No readable text found in this file — if it's a scanned PDF, try a text-based export.",
                )
            resume_text = raw_text
    elif task_id:
        task = _tasks.get(task_id)
        if not task or task.get("status") != "done":
            raise HTTPException(status_code=400, detail="Task not complete or not found")
        _, base_path = _resolve_resume(task.get("resume_id"))
        tex_path = task.get("tex_path") or base_path
        # parse_resume()["plain_text"], not a raw read + strip_latex on the
        # whole file — same fix as /api/compare, for the same reason: the
        # raw file's preamble (documentclass/package options, \newcommand
        # macro definitions) is LaTeX noise the recruiter agent has no use
        # for and would otherwise inflate the analyzed prompt for nothing.
        resume_text = parse_resume(tex_path)["plain_text"]
    else:
        raise HTTPException(status_code=400, detail="Attach a resume file or provide a task_id")

    try:
        recruiter_result = analyze(jd, resume_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

    result = score(recruiter_result, resume_text)
    log.info(
        "ATS check complete  source=%s  score=%s%%",
        "file" if file is not None and file.filename else f"task={task_id}",
        result["overall_score"],
    )
    return result


# ── Resume MD editor endpoints ────────────────────────────────────────────────


def _resume_md_path(tex_path: str) -> Path:
    """The Markdown draft lives next to a resume's `.tex` file."""
    return Path(tex_path).parent / "resume-content.md"


@app.get("/api/resume-md")
def get_resume_md(resume_id: str | None = None):
    """Return the resume content as Markdown. Generates it from main.tex on first call."""
    _, tex_path = _resolve_resume(resume_id)
    md_path = _resume_md_path(tex_path)
    if not md_path.exists():
        from md_converter import tex_to_md

        tex = Path(tex_path).read_text(encoding="utf-8")
        md = tex_to_md(tex)
        md_path.write_text(md, encoding="utf-8")
    return {"content": md_path.read_text(encoding="utf-8")}


class ResumeMdBody(BaseModel):
    """Body for PUT /api/resume-md."""

    content: str
    resume_id: str | None = None


@app.put("/api/resume-md")
def put_resume_md(req: ResumeMdBody):
    """Save the edited Markdown draft next to the resume's `.tex` file."""
    _, tex_path = _resolve_resume(req.resume_id)
    _resume_md_path(tex_path).write_text(req.content, encoding="utf-8")
    return {"saved": True}


class ResumeMdSyncBody(BaseModel):
    """Body for POST /api/resume-md/sync."""

    resume_id: str | None = None


@app.post("/api/resume-md/sync")
def sync_resume_md(req: ResumeMdSyncBody | None = None):
    """Convert the saved Markdown draft → LaTeX, update main.tex, compile PDF."""
    _, tex_path_str = _resolve_resume(req.resume_id if req else None)
    tex_path = Path(tex_path_str)
    md_path = _resume_md_path(tex_path_str)
    if not md_path.exists():
        raise HTTPException(status_code=400, detail="No resume draft found — open the editor first")

    import shutil as _shutil

    from agents.chat_editor import _next_backup_path
    from md_converter import md_to_tex

    md = md_path.read_text(encoding="utf-8")
    original_tex = tex_path.read_text(encoding="utf-8")

    new_tex = md_to_tex(md, original_tex)

    backup = _next_backup_path(tex_path)
    _shutil.copy2(tex_path, backup)
    tex_path.write_text(new_tex, encoding="utf-8")

    try:
        pdf_path = compile_tex(str(tex_path))
    except Exception as exc:
        _shutil.copy2(backup, tex_path)
        raise HTTPException(status_code=500, detail=f"Compile failed — reverted. {exc}") from exc

    edit_id = str(uuid.uuid4())
    _chat_pdfs[edit_id] = pdf_path
    log.info("Resume MD synced  edit_id=%s  pdf=%s", edit_id, pdf_path)
    return {"synced": True, "edit_id": edit_id, "has_pdf": True}


@app.get("/api/template")
def get_template(resume_id: str | None = None) -> FileResponse:
    """Serve the base resume template PDF, recompiling if main.tex changed."""
    _, tex_path = _resolve_resume(resume_id)
    tex = Path(tex_path)
    pdf = tex.with_suffix(".pdf")
    # Recompile if PDF is missing or main.tex has been updated since last compile
    if not pdf.exists() or tex.stat().st_mtime > pdf.stat().st_mtime:
        try:
            compile_tex(str(tex))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Template compile failed: {exc}") from exc
    if not pdf.exists():
        raise HTTPException(status_code=500, detail="Template PDF could not be produced")
    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


# ── Resume history ─────────────────────────────────────────────────────────────


class HistorySaveRequest(BaseModel):
    """Body for POST /api/history."""

    task_id: str
    company_name: str
    job_url: str = ""
    applied_date: str = ""


@app.post("/api/history")
def save_history(req: HistorySaveRequest) -> dict:
    """Save a completed task's resume to history — company name + source URL
    are the only things the user has to supply; everything else (job title,
    score, verdict, PDF, resume identity) is pulled from the already-completed task."""
    task = _tasks.get(req.task_id)
    if not task or task.get("status") != "done" or not task.get("pdf_path"):
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    resume_id, _ = _resolve_resume(task.get("resume_id"))
    entry = history_save(
        resume_id=resume_id,
        company_name=req.company_name.strip(),
        job_title=task.get("recruiter_result", {}).get("job_title", ""),
        job_url=req.job_url.strip(),
        pdf_path=task["pdf_path"],
        ats_score=task.get("score"),
        verdict=task.get("verdict"),
        applied_date=req.applied_date.strip(),
    )
    return {"entry": entry}


@app.get("/api/history")
def get_history(resume_id: str | None = None):
    """Latest-first list of every saved resume for one resume identity."""
    rid, _ = _resolve_resume(resume_id)
    return {"entries": history_list(rid)}


@app.get("/api/history/{entry_id}/pdf")
def get_history_pdf(entry_id: str) -> FileResponse:
    """Serve the PDF for one saved history entry."""
    entry = history_get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    pdf = Path(entry["pdf_path"])
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF file no longer exists on disk")
    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


# ── Verifier agent (exact + semantic keyword matching) ──────────────────────


def _tailored_tex_text(task: dict) -> str:
    # Read the path this task's own pipeline/boost run recorded rather than
    # guessing from what files exist in `out_dir` — that directory is keyed
    # only by job title + date, so two tasks generated the same day for the
    # same role share it, and an existence check can silently return a
    # different task's tailored resume.
    tex_path_str = task.get("tex_path")
    if not tex_path_str:
        raise HTTPException(status_code=400, detail="No tailored resume available for this task")
    tex_path = Path(tex_path_str)
    if not tex_path.exists():
        raise HTTPException(status_code=404, detail="Tailored resume file not found on disk")
    return strip_latex(tex_path.read_text(encoding="utf-8"))


@app.post("/api/verify/{task_id}")
def run_verifier(task_id: str):
    """Re-checks every required/preferred keyword both exactly and semantically."""
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")
    recruiter_result = task.get("recruiter_result")
    if not recruiter_result:
        raise HTTPException(status_code=400, detail="Missing pipeline data — re-generate first")

    resume_text = _tailored_tex_text(task)
    result = verify(recruiter_result, resume_text)
    task["verifier_result"] = result
    log.info("Verifier run  task_id=%s  keywords=%d", task_id, len(result["keywords"]))
    return result


class ExplainRequest(BaseModel):
    """Body for POST /api/verify/{task_id}/explain."""

    keyword: str


@app.post("/api/verify/{task_id}/explain")
def explain(task_id: str, req: ExplainRequest) -> dict:
    """Ad-hoc 'where did you add X' lookup for any keyword, not just the JD's list."""
    task = _tasks.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Task not complete or not found")

    resume_text = _tailored_tex_text(task)
    return explain_keyword(req.keyword.strip(), resume_text)


# ── Email generator ───────────────────────────────────────────────────────────


class EmailGenerateRequest(BaseModel):
    """Body for POST /api/email/generate."""

    job_post: str
    instruction: str = ""
    resume_id: str | None = None
    source_url: str = ""


class EmailReviseRequest(BaseModel):
    """Body for POST /api/email/revise."""

    email_id: str
    instruction: str


class EmailUndoRequest(BaseModel):
    """Body for POST /api/email/undo."""

    email_id: str


class EmailUpdateRequest(BaseModel):
    """Body for POST /api/email/{email_id}/update — direct manual edit,
    bypassing the LLM revise flow."""

    to: str
    subject: str
    body: str


class EmailSaveRequest(BaseModel):
    """Body for POST /api/email/{email_id}/save."""

    company_name: str = ""
    role_title: str = ""
    source_url: str = ""


class EmailSendRequest(BaseModel):
    """Body for POST /api/email/{email_id}/send."""

    to: str


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _resume_plain_text(resume_id: str | None) -> str:
    """Parse a resume identity's base resume and return its plain-text rendering."""
    _, tex_path = _resolve_resume(resume_id)
    resume_data = parse_resume(tex_path)
    return resume_data["plain_text"]


@app.post("/api/email/generate")
def email_generate(req: EmailGenerateRequest) -> dict:
    """Draft an application email from a pasted job post + the base resume."""
    if not req.job_post.strip():
        raise HTTPException(status_code=400, detail="Paste the job post text first")

    resume_id, _ = _resolve_resume(req.resume_id)
    resume_text = _resume_plain_text(resume_id)
    learned = recent_email_patterns(resume_id)
    try:
        result = generate_email(req.job_post, resume_text, req.instruction, learned)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate email: {exc}") from exc

    email_id = str(uuid.uuid4())
    _emails[email_id] = {
        "to": result.get("to", ""),
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "role_title": result.get("role_title", ""),
        "company_name": result.get("company_name", ""),
        "job_post": req.job_post,
        "source_url": req.source_url.strip(),
        "history": [],
        "resume_id": resume_id,
    }
    log.info("Email generated  email_id=%s  role=%s", email_id, result.get("role_title"))
    notify_email_done(result.get("role_title") or "this role")
    return {"email_id": email_id, **_emails[email_id]}


@app.post("/api/email/revise")
def email_revise(req: EmailReviseRequest) -> dict:
    """Apply a chat-style revision instruction to an existing email draft."""
    current = _emails.get(req.email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found — generate one first")
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="Tell me what to change")

    resume_text = _resume_plain_text(current.get("resume_id"))
    try:
        result = revise_email(current, req.instruction, resume_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not revise email: {exc}") from exc

    current["history"].append(
        {"to": current["to"], "subject": current["subject"], "body": current["body"]}
    )
    current["to"] = result.get("to", current["to"])
    current["subject"] = result.get("subject", current["subject"])
    current["body"] = result.get("body", current["body"])
    learn_email_pattern(req.instruction, current["resume_id"])
    log.info("Email revised  email_id=%s", req.email_id)
    return {
        "email_id": req.email_id,
        "to": current["to"],
        "subject": current["subject"],
        "body": current["body"],
        "role_title": current["role_title"],
        "company_name": current["company_name"],
        "done_summary": result.get("done_summary", "Updated the email."),
    }


@app.post("/api/email/undo")
def email_undo(req: EmailUndoRequest) -> dict:
    """Revert an email draft to its previous version."""
    current = _emails.get(req.email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found")
    if not current["history"]:
        raise HTTPException(status_code=400, detail="Nothing to undo")

    prev = current["history"].pop()
    current["to"] = prev["to"]
    current["subject"] = prev["subject"]
    current["body"] = prev["body"]
    return {
        "email_id": req.email_id,
        "to": current["to"],
        "subject": current["subject"],
        "body": current["body"],
    }


@app.post("/api/email/{email_id}/update")
def email_update(email_id: str, req: EmailUpdateRequest) -> dict:
    """Directly overwrite a draft's to/subject/body with a manual edit —
    no LLM call, so the user can fix anything (like a placeholder sign-off)
    themselves without waiting on a revise round-trip."""
    current = _emails.get(email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found")

    current["history"].append(
        {"to": current["to"], "subject": current["subject"], "body": current["body"]}
    )
    current["to"] = req.to
    current["subject"] = req.subject
    current["body"] = req.body
    log.info("Email manually edited  email_id=%s", email_id)
    return {
        "email_id": email_id,
        "to": current["to"],
        "subject": current["subject"],
        "body": current["body"],
        "role_title": current["role_title"],
        "company_name": current["company_name"],
    }


@app.post("/api/email/{email_id}/save")
def email_save(email_id: str, req: EmailSaveRequest) -> dict:
    """Save a finalized email into the career tracker: link or update its
    Apply Later row (status Applied), then auto-populate the topic map and
    interview-prep checklist from the job post's keywords."""
    current = _emails.get(email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found")

    company_name = req.company_name.strip() or current.get("company_name", "")
    role_title = req.role_title.strip() or current.get("role_title", "")
    source_url = req.source_url.strip() or current.get("source_url", "")
    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required to save")

    resume_id = current["resume_id"]
    try:
        resume_text = _resume_plain_text(resume_id)
        summary = save_email_context(
            email_id=email_id,
            resume_id=resume_id,
            company_name=company_name,
            role_title=role_title,
            to_addr=current["to"],
            subject=current["subject"],
            body=current["body"],
            source_url=source_url,
            job_post_text=current.get("job_post", ""),
            resume_plain_text=resume_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save email: {exc}") from exc
    current["company_name"] = company_name
    current["role_title"] = role_title
    current["source_url"] = source_url
    log.info(
        "Email saved  email_id=%s  company=%s  apply_later_id=%s",
        email_id,
        company_name,
        summary["apply_later_id"],
    )
    return {"email_id": email_id, "company_name": company_name, "role_title": role_title, **summary}


@app.post("/api/email/{email_id}/send")
def email_send(email_id: str, req: EmailSendRequest) -> dict:
    """Send a finalized email over Gmail SMTP with the current resume
    attached as a freshly compiled PDF."""
    current = _emails.get(email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found")

    to_addr = req.to.strip()
    if not _EMAIL_RE.match(to_addr):
        raise HTTPException(status_code=400, detail="Enter a valid recipient email address")

    resume_id = current["resume_id"]
    _, tex_path = _resolve_resume(resume_id)
    resume = get_resume(resume_id)
    label = (resume or {}).get("label") or "resume"
    safe_name = re.sub(r"[^\w\-]", "_", label)

    try:
        pdf_path = compile_tex(tex_path)
        pdf_bytes = Path(pdf_path).read_bytes()
        send_email(
            to_addr=to_addr,
            subject=current["subject"],
            body=current["body"],
            pdf_bytes=pdf_bytes,
            pdf_filename=f"{safe_name}.pdf",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not send email: {exc}") from exc

    log.info("Email sent  email_id=%s  to=%s", email_id, to_addr)
    return {"email_id": email_id, "to": to_addr}


@app.get("/api/email/{email_id}/download")
def email_download(email_id: str) -> Response:
    """Download an email draft as a .eml file."""
    current = _emails.get(email_id)
    if not current:
        raise HTTPException(status_code=404, detail="Email draft not found")

    eml_content = (
        f"To: {current['to']}\r\n"
        f"Subject: {current['subject']}\r\n"
        f"Content-Type: text/plain; charset=UTF-8\r\n"
        f"\r\n"
        f"{current['body']}\r\n"
    )
    safe_name = re.sub(r"[^\w\-]", "_", current.get("role_title") or "email")
    return Response(
        content=eml_content,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.eml"'},
    )
