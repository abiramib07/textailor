# TexTailor — Session Continuation Guide

> Written: 2026-06-20 | Pick up from here in the next Claude session.

---

## What This Project Is

**TexTailor** — An automated AI resume tailoring tool.
- You paste a job description into `jd_input.txt`
- The tool reads your LaTeX resume from `resume/main.tex`
- Runs it through a 5-step AI pipeline (parse → keyword gap → rewrite → compile → score)
- Outputs a tailored `resume_tailored.pdf` + `ats_report.txt` in `output/[JobTitle]_[Date]/`

**GitHub repo:** `https://github.com/abiramib07/textailor` (private)
**Local path:** `D:\AI resume automater\`
**Active branch:** `dev` (develop here, merge to `main` when stable)

---

## Current Status (as of session end)

### What is FULLY DONE and committed to `dev`:

| File | Status | What it does |
|------|--------|-------------|
| `resume/main.tex` | Done | Master LaTeX resume — never auto-modified |
| `src/latex_parser.py` | Done + tested | Reads `.tex`, extracts sections by `\header{}`, converts to plain text |
| `src/claude_client.py` | Done + tested | Calls `claude --print` via stdin pipe (uses Pro subscription, no API key) |
| `src/agents/recruiter.py` | Done + tested | Analyzes JD vs resume, returns keyword gap JSON |
| `src/agents/rewriter.py` | Done + tested | Rewrites LaTeX sections with JD keywords + Google XYZ formula |
| `src/agents/ats_scorer.py` | Done | Computes ATS match %, writes report |
| `src/latex_patcher.py` | Done | Patches rewritten sections back into `.tex` copy |
| `src/compiler.py` | Done | Runs `pdflatex` to compile `.tex` → `.pdf` |
| `src/main.py` | Done | File watcher + full pipeline orchestrator |
| `config.json` | Done | All paths and settings configured |

### What was IN PROGRESS at session end:

**Full end-to-end pipeline test** was running when session ended.
- The pipeline completed steps 1–4 (parse, recruiter, rewriter, patch LaTeX)
- `output/AI_ML_Engineer_2026-06-20/resume_tailored.tex` was produced ✓
- `output/AI_ML_Engineer_2026-06-20/resume_tailored.log` was produced ✓
- PDF compilation was in progress — MiKTeX was auto-downloading packages (normal on first run)
- **The PDF may or may not have been produced** — check `output/AI_ML_Engineer_2026-06-20/` for `resume_tailored.pdf`

---

## First Thing To Do Next Session

### Step 1 — Check if PDF was produced
Open: `D:\AI resume automater\output\AI_ML_Engineer_2026-06-20\`
- If `resume_tailored.pdf` exists → pipeline is fully working, skip to "Remaining Work"
- If only `.tex` and `.log` exist → re-run the test (see below)

### Step 2 — Re-run the test if needed
Open a terminal in `D:\AI resume automater\` and run:

```python
# Save this as test_run.py and run: python test_run.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path("src")))
import re
from main import run_pipeline, load_config

jd = """
AI/ML Engineer - Bangalore (Hybrid)
Requirements:
- Python, PyTorch, TensorFlow
- Fine-tuning LLMs using LoRA, QLoRA, PEFT
- Building RAG pipelines with LangChain or LlamaIndex
- Vector databases: Pinecone, Weaviate, Chroma
- FastAPI REST API development
- Prompt engineering and LLM evaluation techniques
- Git, Docker, Azure cloud
Nice to have:
- LangGraph, multi-agent framework experience
- MLOps practices and CI/CD for ML pipelines
- AWS experience
"""

config = load_config()
run_pipeline(jd, config)
```

---

## Remaining Work (in order)

### 1. Verify PDF output quality
- Open `resume_tailored.pdf` and visually check:
  - Does it look the same as the original template?
  - Are the new keywords visible in the right places?
  - Is the formatting preserved?

### 2. Fix any LaTeX compile errors
- If pdflatex fails on AI-generated content, the rewriter prompt needs tightening
- Key constraint to add: "Never use \textbf{} around multi-line content"
- Check `resume_tailored.log` for `!` error lines

### 3. Implement `src/notifier.py` — Windows toast notification
```python
from plyer import notification

def notify(title: str, message: str):
    notification.notify(
        title=title,
        message=message,
        app_name="TexTailor",
        timeout=8
    )
```
- Call `notify("Resume Ready!", f"{score}% ATS match — {job_title}")` at end of `run_pipeline()`

### 4. Wire up the file watcher (final automation step)
- Run `python src/main.py` to start the watcher
- Test by pasting a JD into `jd_input.txt` and saving
- Should trigger the full pipeline automatically

### 5. Fix `%NEEDS_METRIC` bullets
- The rewriter flags bullets with no quantifiable result as `%NEEDS_METRIC`
- These appear as LaTeX comments in the output — ATS-safe but visually invisible
- Need a post-process step to either strip the flag or surface them in the ATS report

### 6. Commit all work to dev, then merge to main
```bash
git add -A
git commit -m "Phase 2-5: full pipeline working end-to-end"
git push origin dev

# Then merge to main when satisfied
git checkout main
git merge dev
git push origin main
```

---

## Key Technical Decisions Made

| Decision | Detail |
|----------|--------|
| AI backend | `claude --print` via stdin pipe (no API key — uses Pro subscription) |
| Claude CLI path | `C:\Users\ELCOT\AppData\Roaming\npm\claude.cmd` |
| LaTeX section marker | `\header{}` (NOT `\section{}`) — custom command in this template |
| pdflatex path | `C:\Users\ELCOT\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe` |
| Section parsing | Regex: `\\header\{Name\}(.*?)(?=\\header\{|\end\{document\})` with `re.DOTALL` |
| Replacement strategy | Lambda in `re.sub` (avoids backslash escape issues in LaTeX replacements) |
| Trigger | `watchdog` watching `jd_input.txt` for file save events |

---

## File Structure
```
D:\AI resume automater\
├── CONTINUE_HERE.md          ← YOU ARE HERE
├── design_plan.md            ← full architecture doc
├── prompt.md.txt             ← original 4-skill prompt guide (knowledge base)
├── jd_input.txt              ← PASTE JD HERE to trigger pipeline
├── config.json               ← all paths and settings
├── requirements.txt          ← watchdog, plyer
├── resume/
│   └── main.tex              ← master LaTeX resume (NEVER auto-modified)
├── output/
│   └── AI_ML_Engineer_2026-06-20/
│       ├── resume_tailored.tex   ← patched LaTeX (produced in last test)
│       ├── resume_tailored.log   ← pdflatex log
│       └── resume_tailored.pdf   ← CHECK IF THIS EXISTS
└── src/
    ├── main.py               ← entry point + file watcher
    ├── latex_parser.py       ← section extractor
    ├── claude_client.py      ← Claude CLI caller
    ├── latex_patcher.py      ← rewrites sections back into .tex
    ├── compiler.py           ← pdflatex runner
    ├── notifier.py           ← TODO: implement toast notification
    └── agents/
        ├── diagnoser.py      ← TODO: implement (ATS structural check)
        ├── recruiter.py      ← done: keyword gap analysis
        ├── rewriter.py       ← done: LaTeX rewriter with XYZ formula
        └── ats_scorer.py     ← done: ATS match scoring
```

---

## How to Resume With Claude

Start the next session by saying something like:

> "I'm continuing the TexTailor project at D:\AI resume automater\
> Read CONTINUE_HERE.md and design_plan.md to get up to speed,
> then help me with [next task from Remaining Work above]"

Claude will read both files and have full context to continue immediately.
