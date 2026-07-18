# TexTailor — How to Start the Application

---

## Prerequisites

Make sure the following are installed before running the app.

| Tool | Version | Check |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Angular CLI | 17+ | `ng version` |
| MiKTeX (pdflatex) | any | `pdflatex --version` |
| Claude Code CLI | latest | `claude --version` |
| Windows Terminal | any | (from Microsoft Store) |

**First-time Python setup** (run once):
```powershell
cd "D:\AI resume automater"
pip install fastapi uvicorn watchdog plyer
```

**First-time Node setup** (run once):
```powershell
cd "D:\AI resume automater\ui"
npm install
```

**Claude Code must be logged in** (run once):
```powershell
claude login
```
All AI calls go through your Claude Pro account — no API key needed.

---

## Starting the App

### Option A — One command (recommended)

Requires **Windows Terminal** to be installed.

```powershell
powershell -File "D:\AI resume automater\start.ps1"
```

This opens Windows Terminal with two tabs automatically:
- **Tab 1 `BACKEND :8000`** — FastAPI server + pipeline logs
- **Tab 2 `FRONTEND :4200`** — Angular dev server

The browser opens at `http://localhost:4200` automatically after ~10 seconds.

---

### Option B — Two separate PowerShell windows

**Window 1 — Backend:**
```powershell
cd "D:\AI resume automater"
python -m uvicorn src.api:app --reload --port 8000 --log-level info
```

**Window 2 — Frontend:**
```powershell
cd "D:\AI resume automater\ui"
ng serve --open
```

---

## URLs

| Service | URL | Purpose |
|---|---|---|
| UI | `http://localhost:4200` | Main app — use this |
| API docs | `http://localhost:8000/docs` | Swagger UI for all routes |
| API base | `http://localhost:8000` | FastAPI backend |

---

## Using the App

### Generate a tailored resume

1. Open `http://localhost:4200`
2. Paste a job description into the **Job Description** box
3. Click **Tailor My Resume**
4. Wait 45–90 seconds — the pipeline runs 5 steps:
   - Parse resume sections
   - Analyse JD keywords (Claude)
   - Rewrite sections with missing keywords (Claude)
   - Compile PDF with pdflatex
   - Score ATS match
5. PDF appears on the right. Score card + keyword report appear on the left.
6. If score < 90% → click **Boost to 90%+** to auto-weave missing keywords.

### Edit resume via chat

After a PDF is generated, the **Edit via Chat** panel appears below the PDF.

- Type a change request: *"make it 2 pages"*, *"remove SCQA project"*, *"increase font size"*
- Claude shows a plan — review it
- Click **Yes, apply changes** to execute
- PDF updates automatically
- Click **↩ Undo** to revert any chat change

### Edit resume content (Markdown editor)

1. Click the **Resume Editor** tab in the header
2. First open takes ~30–60 s (Claude converts LaTeX → Markdown, one-time only)
3. Edit the Markdown — add projects, update bullets, fix skills
4. Click **Save Draft** when done
5. Click **Sync with Resume Template** — Claude converts back to LaTeX and compiles (~60 s)
6. Download the updated PDF from the sidebar

### Add pending edits before a run

Paste raw project/bullet content into `inputs/pending-edits.md`.  
The agent picks it up automatically at the start of every pipeline run, analyses it, and asks for terminal confirmation before patching.

### View your base resume template

Click **View Template** in the top-right corner of the Generator tab.

---

## Stopping the App

In each terminal window press `Ctrl + C`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pdflatex not found` | Install MiKTeX from [miktex.org/download](https://miktex.org/download) |
| `claude: command not found` | Run `npm install -g @anthropic-ai/claude-code` then `claude login` |
| `ng: command not found` | Run `npm install -g @angular/cli` |
| Backend starts but UI shows API error | Make sure backend is running on port 8000 before opening the browser |
| ATS score is 0% | Check that the pipeline completed all 5 steps — look at the stepper in the UI |
| Template PDF shows blank | Click View Template again — backend recompiles automatically if main.tex changed |
| `Port 8000 already in use` | Run `netstat -ano \| findstr :8000` then `taskkill /PID <pid> /F` |
| `Port 4200 already in use` | Run `ng serve --port 4201` instead |
