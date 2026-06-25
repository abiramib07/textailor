# TexTailor — UI Setup & Status

## What Was Built

### Backend — `src/api.py` (FastAPI)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/generate` | POST | Accepts JD text, runs 5-step pipeline in background thread |
| `/api/status/{task_id}` | GET | Poll for live progress + results |
| `/api/pdf/{task_id}` | GET | Serves the tailored PDF |
| `/api/template` | GET | Serves the base resume PDF |

### Frontend — `ui/` (Angular 22)

- Left panel: JD textarea + Generate button + live progress log + ATS score badge
- Right panel: inline PDF viewer with Download button
- "View Template" button in header to preview your base resume

---

## MiKTeX Fix Applied

**Problem:** pdflatex was blocking in nonstop mode when packages were missing.

**Fix applied (permanent):**
```powershell
initexmf --set-config-value "[MPM]AutoInstall=1"
```
All future compiles will auto-download missing packages without blocking.

**Packages installed during fix:**
- `ltxcmds` — was missing, now installed
- `kvsetkeys`, `etoolbox`, `oberdiek` — were already present

---

## Current State

| Item | Status |
|---|---|
| `resume/main.pdf` | Compiled — "View Template" button works |
| `output/AI_ML_Engineer_2026-06-20/resume_tailored.pdf` | 2-page PDF confirmed working |
| Angular UI (`ui/`) | Built, zero compile errors |
| FastAPI backend (`src/api.py`) | Ready |
| MiKTeX auto-install | Enabled permanently |

---

## How to Launch

### One-shot (recommended)
```powershell
powershell -File "D:\AI resume automater\start.ps1"
```
Opens two terminal windows automatically — browser launches at `http://localhost:4200`.

### Manual (two terminals)
```powershell
# Terminal 1 — Backend
cd "D:\AI resume automater"
uvicorn src.api:app --reload --port 8000

# Terminal 2 — Frontend
cd "D:\AI resume automater\ui"
ng serve --open
```

| Service | URL |
|---|---|
| Angular UI | http://localhost:4200 |
| FastAPI backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

---

## How to Use

1. Run `start.ps1` — browser opens automatically
2. Paste a full job description into the left panel
3. Click **Generate Resume**
4. Watch the live progress log (5 steps: parse → recruit → rewrite → compile → score)
5. PDF appears in the right panel when done
6. Click **Download PDF** to save
7. Click **View Template** in the header anytime to preview your base resume

---

## File Structure (UI additions)

```
D:\AI resume automater\
├── start.ps1                 ← one-shot launcher (backend + frontend)
├── src/
│   └── api.py                ← FastAPI backend
├── resume/
│   ├── main.tex              ← master LaTeX resume
│   └── main.pdf              ← compiled template PDF (for View Template)
└── ui/                       ← Angular 22 app
    ├── src/
    │   └── app/
    │       ├── app.ts        ← main component logic
    │       ├── app.html      ← UI template
    │       ├── app.scss      ← dark theme styles
    │       ├── app.config.ts ← HttpClient provider
    │       └── resume.service.ts ← API calls + polling
    └── dist/ui/              ← production build output
```
