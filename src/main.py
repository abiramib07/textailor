import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

sys.path.insert(0, str(Path(__file__).parent))

from agents.ats_scorer import score, write_report
from agents.recruiter import analyze
from agents.rewriter import rewrite
from compiler import compile_tex
from latex_parser import parse_resume, strip_latex
from latex_patcher import write_tailored_tex


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(jd_text: str, config: dict) -> None:
    print("\n" + "=" * 60)
    print(f"TexTailor pipeline started — {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

    # ── Step 1: Parse master resume ──────────────────────────────
    print("\n[1/5] Parsing resume...")
    resume_data = parse_resume(config["resume_path"])
    print(f"      Sections: {list(resume_data['sections'].keys())}")

    # ── Step 2: Recruiter — keyword gap analysis ──────────────────
    print("\n[2/5] Analysing job description (Recruiter Agent)...")
    recruiter_result = analyze(jd_text, resume_data["plain_text"])
    job_title = recruiter_result.get("job_title", "Role")
    print(f"      Role: {job_title}")
    print(f"      Required keywords missing: {len(recruiter_result['missing_from_resume'])}")
    print(f"      Priority adds: {recruiter_result['priority_adds'][:5]}...")

    # ── Step 3: Rewriter — tailor resume ─────────────────────────
    print("\n[3/5] Rewriting resume sections (Rewriter Agent)...")
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
    print(f"      Sections rewritten: {list(rewritten.keys())}")

    # ── Step 4: Patch .tex and compile PDF ───────────────────────
    print("\n[4/5] Patching LaTeX and compiling PDF...")
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
    print(f"      PDF: {pdf_path}")

    # ── Step 5: ATS Score report ──────────────────────────────────
    print("\n[5/5] Scoring ATS match...")
    rewritten_plain = "\n".join(
        strip_latex(content) for content in rewritten.values()
    )
    score_result = score(recruiter_result, rewritten_plain)
    report_path = str(out_dir / "ats_report.txt")
    write_report(score_result, report_path)

    # ── Done ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"DONE — {score_result['overall_score']}% ATS match — {score_result['verdict']}")
    print(f"Output: {out_dir}")
    print("=" * 60)

    if config.get("auto_open_output", True):
        os.startfile(str(out_dir))


class JDFileHandler(FileSystemEventHandler):
    def __init__(self, jd_path: str, config: dict):
        self.jd_path = Path(jd_path).resolve()
        self.config = config
        self._last_run = 0

    def on_modified(self, event):
        if Path(event.src_path).resolve() != self.jd_path:
            return
        # Debounce — ignore repeated events within 3 seconds
        now = time.time()
        if now - self._last_run < 3:
            return
        self._last_run = now

        jd_text = self.jd_path.read_text(encoding="utf-8").strip()
        placeholder = "PASTE JOB DESCRIPTION HERE"
        if not jd_text or jd_text.startswith(placeholder):
            return

        try:
            run_pipeline(jd_text, self.config)
        except Exception as exc:
            print(f"\n[ERROR] Pipeline failed: {exc}")


import re  # noqa: E402 — needed by run_pipeline


def main():
    config = load_config()
    jd_path = config["jd_input_path"]

    print("TexTailor is watching for job descriptions...")
    print(f"  Drop JD into: {jd_path}")
    print("  Press Ctrl+C to stop.\n")

    handler = JDFileHandler(jd_path, config)
    observer = Observer()
    observer.schedule(handler, path=str(Path(jd_path).parent), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
