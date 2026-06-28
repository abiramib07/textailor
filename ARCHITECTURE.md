# TexTailor — Architecture

**AI Resume Automator** · Python + FastAPI backend · Angular 17 frontend · Claude Code CLI for all AI

---

## Overview

TexTailor takes a job description and your LaTeX resume, runs a 5-step AI pipeline to tailor and score it, and serves the result as a live PDF in the browser. It also supports direct resume editing via chat or a Markdown editor tab.

```
Browser (Angular 17)
      │  HTTP/REST
      ▼
FastAPI  (src/api.py · port 8000)
      │
      ├── Pipeline thread (per JD run)
      │     1. latex_parser   →  extract sections from main.tex
      │     2. recruiter      →  Claude: keyword gap analysis
      │     3. rewriter       →  Claude: rewrite sections with missing keywords
      │     4. latex_patcher  →  stitch rewritten sections back into .tex
      │     5. compiler       →  pdflatex × 2 → PDF
      │     6. ats_scorer     →  regex keyword match → score %
      │
      ├── Chat editor  (agents/chat_editor.py)
      │     plan()    →  Claude: describe what will change (no file writes)
      │     execute() →  Claude: generate LaTeX patches → backup → apply → compile
      │     undo()    →  restore latest inputs/backups/vN.tex → compile
      │
      ├── Resume MD editor  (src/md_converter.py)
      │     tex_to_md()  →  Claude: main.tex → Markdown (one-time seed)
      │     md_to_tex()  →  Claude: Markdown → LaTeX body (preamble preserved)
      │
      └── Pending-edits agent  (agents/editor.py)
            reads inputs/pending-edits.md → Claude analysis → terminal confirm → patch
```

---

## Directory Layout

```
D:\AI resume automater\
│
├── config.json                  ← runtime paths + pipeline settings
├── requirements.txt             ← Python dependencies
├── start.ps1                    ← one-command launcher (opens 2 terminal tabs)
├── start-backend.ps1            ← uvicorn src.api:app --reload --port 8000
├── start-frontend.ps1           ← ng serve --open
│
├── resume/
│   ├── main.tex                 ← master resume (source of truth)
│   ├── main.pdf                 ← compiled template PDF
│   └── resume-content.md        ← Markdown mirror (auto-generated on first Edit tab open)
│
├── inputs/
│   ├── pending-edits.md         ← drop zone: paste raw content → agent processes it
│   ├── backups/                 ← numbered undo chain: v1.tex, v2.tex, …
│   └── processed/               ← archived applied pending-edits (YYYY-MM-DD-slug.md)
│
├── output/
│   └── <Role>_<YYYY-MM-DD>/
│       ├── resume_tailored.tex  ← patched LaTeX (pipeline output)
│       ├── resume_tailored.pdf  ← compiled PDF served to browser
│       ├── resume_boosted.tex   ← ATS boost output (if triggered)
│       ├── resume_boosted.pdf
│       ├── ats_report.txt       ← full keyword breakdown
│       └── ats_report_boosted.txt
│
├── src/
│   ├── api.py                   ← FastAPI app + all HTTP routes
│   ├── main.py                  ← CLI entry point (non-server runs)
│   ├── claude_client.py         ← subprocess wrapper around claude.cmd
│   ├── latex_parser.py          ← parse main.tex → sections dict + plain text
│   ├── latex_patcher.py         ← stitch rewritten sections back into .tex
│   ├── compiler.py              ← pdflatex × 2 with auto-install (MiKTeX)
│   ├── md_converter.py          ← tex_to_md / md_to_tex (preamble-safe)
│   ├── notifier.py              ← desktop notification on pipeline finish
│   └── agents/
│       ├── recruiter.py         ← Claude: JD → keyword gap JSON
│       ├── rewriter.py          ← Claude: rewrite resume sections with XYZ formula
│       ├── ats_scorer.py        ← regex keyword match → score % (no AI)
│       ├── chat_editor.py       ← two-phase chat: plan() + execute() + undo()
│       ├── editor.py            ← pending-edits drop zone agent
│       └── diagnoser.py         ← (unused) LaTeX error diagnoser
│
├── ui/                          ← Angular 17 standalone app
│   └── src/app/
│       ├── app.ts               ← root component + all state machines
│       ├── app.html             ← two-tab layout: Generate + Edit Resume
│       ├── app.scss             ← all styles
│       └── resume.service.ts    ← typed HTTP client for all API routes
│
└── session-history/
    └── 28-06-2026.md            ← detailed log of session features built
```

---

## AI Layer — Claude Code CLI

All AI calls go through **`src/claude_client.py`**. There is no direct Anthropic API key — it pipes prompts to `claude.cmd` (npm-installed Claude Code CLI) which uses the logged-in Claude Pro subscription.

```python
subprocess.run(
    ["cmd", "/c", "claude.cmd", "--print", "--output-format", "text"],
    input=prompt,   # prompt sent via stdin (avoids Windows cmd-line length limits)
    ...
)
```

Every agent follows the same pattern: build a text prompt → `ask_claude(prompt)` → parse the response.

---

## Pipeline (5 Steps)

| # | Step | File | AI? | Output |
|---|---|---|---|---|
| 1 | Parse resume | `latex_parser.py` | No | `sections` dict + `plain_text` |
| 2 | Analyse JD | `agents/recruiter.py` | Claude | `required_keywords`, `missing_from_resume`, `priority_adds`, `key_action_verbs` |
| 3 | Rewrite sections | `agents/rewriter.py` | Claude | rewritten LaTeX per section (ampersands auto-escaped) |
| 4 | Compile PDF | `latex_patcher.py` + `compiler.py` | No | `resume_tailored.pdf` |
| 5 | Score ATS | `agents/ats_scorer.py` | No | `overall_score`, keyword breakdown |

Steps run in a daemon thread per `task_id`. The frontend polls `/api/status/{task_id}` every 1.5 s.

### LaTeX section matching

`latex_parser.py` finds sections with:
```
\section*?\{SectionName\}  …body…  \section*?\{Next\}
```
`latex_patcher.py` replaces the body between those markers with the rewriter output.

**Locked sections** (config `sections_to_lock`): Education is never rewritten.

---

## API Routes

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/generate` | Start tailoring pipeline; returns `task_id` |
| `GET` | `/api/status/{task_id}` | Poll pipeline progress + step statuses |
| `GET` | `/api/pdf/{task_id}` | Download tailored PDF |
| `GET` | `/api/report/{task_id}` | Full ATS keyword breakdown JSON |
| `POST` | `/api/boost/{task_id}` | Re-run rewriter with all missing keywords |
| `GET` | `/api/template` | Download base resume PDF (compiles if needed) |
| `POST` | `/api/chat/plan` | Phase 1: analyse edit intent, no file changes |
| `POST` | `/api/chat/execute` | Phase 2: apply confirmed LaTeX patches + compile |
| `GET` | `/api/chat/pdf/{edit_id}` | Serve PDF from chat edit or boost |
| `POST` | `/api/chat/undo` | Revert main.tex to last backup + recompile |
| `GET` | `/api/resume-md` | Load resume as Markdown (generates on first call) |
| `PUT` | `/api/resume-md` | Save Markdown draft to resume-content.md |
| `POST` | `/api/resume-md/sync` | Convert MD → LaTeX, update main.tex, compile |

---

## Frontend State Machines

### Generate tab

```
idle
  → [user clicks Generate]
running  (polls /api/status every 1.5s)
  → done  → loads PDF iframe + fetches /api/report
  → error → shows error box
```

### Chat editor (within Generate tab)

```
idle
  → [user sends message]  chatState = 'planning'
  → /api/chat/plan returns  chatState = 'awaiting_confirmation'
  → [Yes, apply]  chatState = 'executing'
  → /api/chat/execute returns  chatState = 'idle'  (PDF refreshes)
  → [No, cancel]  chatState = 'idle'
```

### Edit Resume tab

```
idle
  → [tab click]  editorState = 'loading'
  → GET /api/resume-md  editorState = 'editing'
  → [user types]  (unsaved badge shows if mdContent ≠ mdOriginal)
  → [Save Draft]  editorState = 'saving' → 'saved'
  → [Sync with Resume Template]  editorState = 'syncing' → 'synced'  (PDF preview appears)
  → [Discard]  rolls back mdContent to mdOriginal  editorState = 'editing'
```

---

## Key Design Decisions

**Preamble safety** — `md_to_tex()` splits `.tex` at `\begin{document}`, sends only the body to Claude, and stitches the original preamble back. LaTeX packages and macro definitions (`\jobheading`, `\bulletitem`, `\projectheading`, `\techline`, `\bulletpoints`) are never regenerated.

**Auto-revert on compile failure** — chat edits and MD sync both copy a backup before writing. If `pdflatex` fails, `shutil.copy2(backup, main.tex)` restores the file automatically.

**Undo chain** — backups are numbered `inputs/backups/v1.tex`, `v2.tex`, … Undo pops the latest, restores it, deletes the backup file, and recompiles.

**LaTeX escaping** — rewriter prompt requires `& → \&`, `% → \%`, `# → \#`. A post-process regex `(?<!\\)&` in `_escape_ampersands()` catches any the model misses. Source `main.tex` must also use `\&` for ampersands in text (e.g. `P\&L`).

**PDF serving** — `activePdfUrl` in the frontend uses the priority chain `boostPdfUrl ?? chatPdfUrl ?? pdfUrl` so the most recently produced PDF is always shown. All non-pipeline PDFs (chat edits, boost, sync) are registered in `_chat_pdfs: dict` and served via `/api/chat/pdf/{edit_id}`.

**No API key** — Claude is invoked through the locally installed `claude.cmd` CLI, which runs under the user's Claude Pro account. The backend never stores credentials.

---

## Running the App

```powershell
# One command (Windows Terminal required — opens two tabs)
powershell -File "D:\AI resume automater\start.ps1"

# Or manually in two PowerShell windows:
# Window 1
python -m uvicorn src.api:app --reload --port 8000

# Window 2
cd ui && ng serve --open
```

- Frontend: `http://localhost:4200`
- API docs (Swagger): `http://localhost:8000/docs`

---

## config.json

```json
{
  "resume_path": "D:\\AI resume automater\\resume\\main.tex",
  "jd_input_path": "D:\\AI resume automater\\jd_input.txt",
  "output_dir": "D:\\AI resume automater\\output",
  "auto_open_output": true,
  "target_ats_score": 95,
  "latex_compiler": "pdflatex",
  "sections_to_rewrite": ["Career Objective", "Experience", "Projects", "Skills"],
  "sections_to_lock": ["Education"]
}
```

> `sections_to_rewrite` should match the actual `\section{...}` names in `main.tex`.  
> Current sections in main.tex: `Professional Summary`, `Technical Skills`, `Experience`, `Education`.
