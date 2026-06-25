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
from agents.recruiter import analyze
from agents.rewriter import rewrite
from compiler import compile_tex
from latex_parser import parse_resume, strip_latex
from latex_patcher import write_tailored_tex
from main import load_config

# ── Logging ───────────────────────────────────────────────────────────────────
# Don't call basicConfig here — uvicorn configures the root logger at startup.
# Our named logger inherits uvicorn's handlers automatically.
log = logging.getLogger("textailor")

app = FastAPI(title="TexTailor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# task_id -> task state
_tasks: dict = {}

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

        # Step 5 — ATS score
        t = _start_step(task_id, 4)
        rewritten_plain = "\n".join(strip_latex(c) for c in rewritten.values())
        score_result = score(recruiter_result, rewritten_plain)
        write_report(score_result, str(out_dir / "ats_report.txt"))
        _done_step(task_id, 4, t, f"{score_result['overall_score']}% — {score_result['verdict']}")

        total = time.perf_counter() - pipeline_start
        log.info("Pipeline complete  %.1fs  score=%s%%  %s", total, score_result["overall_score"], score_result["verdict"])

        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["pdf_path"] = pdf_path
        _tasks[task_id]["score"] = score_result["overall_score"]
        _tasks[task_id]["verdict"] = score_result["verdict"]

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
    return FileResponse(str(pdf), media_type="application/pdf", filename="resume_tailored.pdf")


@app.get("/api/template")
def get_template():
    config = load_config()
    template_dir = Path(config["resume_path"]).parent
    pdf = template_dir / "main.pdf"
    if not pdf.exists():
        compiled = compile_tex(config["resume_path"])
        if not compiled or not Path(compiled).exists():
            raise HTTPException(status_code=500, detail="Template PDF could not be compiled")
        pdf = Path(compiled)
    return FileResponse(str(pdf), media_type="application/pdf", filename="resume_template.pdf")
