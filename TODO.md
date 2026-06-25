# TexTailor — TODO (2026-06-25)

## Status going into today
All backend pipeline fixes and frontend change-detection fixes are in place.
**Not yet tested end-to-end after all fixes** — do this first thing.

---

## 1. Morning: Smoke-test the current build

### Start servers
```powershell
powershell -File "D:\AI resume automater\start.ps1"
```

### Test checklist
- [ ] Browser opens at http://localhost:4200
- [ ] Open DevTools → Console (F12) before doing anything
- [ ] Hard refresh: Ctrl + Shift + R
- [ ] Paste a real job description and click **Generate**
- [ ] Console shows `[TexTailor] generate() called` immediately
- [ ] Console shows `[TexTailor] task created: <uuid>` within 1-2s
- [ ] Console shows `[TexTailor] poll →` lines every 1.5s
- [ ] Stepper appears and steps tick from pending → running → done visually
- [ ] Elapsed timer counts up (e.g. "12s", "1m 5s") during generation
- [ ] After ~3-4 min: PDF appears in right panel
- [ ] ATS score badge shows (was 33% last run — should improve once prompt is tuned)
- [ ] Download button downloads the PDF
- [ ] **View Template** button works (shows base resume PDF)
- [ ] **View Template** is disabled during generation

### If Console shows logs but UI still doesn't update
→ ChangeDetection is broken. Open an issue here and escalate.

### Known slow step
Step 3 "Rewrite sections" takes **~3 minutes** — this is expected.
Claude CLI processes 4 sections serially. Do not assume it's frozen.

---

## 2. Resume Editor Tab — Feature Spec

### What it does
A new "My Resume" tab in the top nav. Opens a plain Markdown editor
showing the user's resume content. User can add/edit bullet points under
existing headings or add new headings. After editing → Save or Discard.
After Save → option to "Sync to Template" which writes the changes into
the live LaTeX resume (`resume/main.tex`) so the next Generate uses it.

### Files involved
| File | Purpose |
|---|---|
| `resume/resume.md` | Source of truth for resume content (human-editable) |
| `resume/main.tex` | LaTeX template compiled to PDF — kept in sync with resume.md |
| `src/api.py` | Add GET /api/resume and POST /api/resume endpoints |
| `ui/src/app/editor/` | New Angular component for the editor tab |

### User flow
```
[My Resume tab]
       ↓
  Markdown editor loads resume.md content
       ↓
  User edits bullet points / adds new points under headings
       ↓
  [Save]  →  shows preview panel  →  [Sync to Template] or [Discard]
  [Discard]  →  reverts to last saved state
       ↓ (Sync to Template)
  Backend converts resume.md sections → updates resume/main.tex
  Confirmation toast: "Template updated — next Generate will use this resume"
```

### Backend endpoints to add
```python
GET  /api/resume          # returns resume.md content as plain text
POST /api/resume          # saves new resume.md content
POST /api/resume/sync     # converts resume.md → updates main.tex sections
```

### Sync logic (resume.md → main.tex)
Each `## Heading` in resume.md maps to a named section in main.tex.
The sync replaces bullet content within that section's LaTeX block.
Headings supported:
- `## Experience` → `\section{Experience}` block
- `## Projects` → `\section{Projects}` block
- `## Skills` → `\section{Skills}` block
- `## Education` → `\section{Education}` block

### Angular editor component
- Textarea bound to resume.md content (raw markdown)
- Toolbar: bold, bullet point helpers (simple, not a full WYSIWYG)
- Character/line count
- Side-by-side: raw MD on left, rendered preview on right (using marked.js)
- Save → POST /api/resume
- Sync → POST /api/resume/sync + success toast

---

## 3. ATS Score Improvement (after editor is working)

Current score: 33% — too low. Target: > 90%.

### Root causes to investigate
- [ ] Rewriter prompt may not be injecting enough JD keywords into resume
- [ ] Skills section may not be getting updated to match JD tech stack
- [ ] ATS scorer prompt may be too strict — verify it's counting correctly

### Plan
1. Check `src/pipeline/` (or api.py) rewriter prompt — add instruction:
   "Incorporate all missing keywords naturally. Prioritise exact-match terms."
2. Add a dedicated Skills sync step: extract skills from JD → add to Skills section
3. Re-run scorer with the same JD to validate improvement

---

## 4. Character encoding fix (low priority)

Step detail shows `"Â·"` instead of `"·"` (middle dot).
Root cause: Claude CLI outputs UTF-8, subprocess reads as Latin-1.
Fix: add `encoding='utf-8'` to the subprocess pipe in api.py.

---

## Done (don't redo)
- [x] FastAPI backend with 5-step pipeline
- [x] Angular 22 standalone UI with stepper + progress bar
- [x] zone.js + provideZoneChangeDetection() wired up
- [x] ChangeDetectorRef.detectChanges() after every state mutation
- [x] Polling replaced with explicit setTimeout loop (no RxJS chain)
- [x] MiKTeX auto-install enabled
- [x] Windows Terminal two-tab launcher (start.ps1)
- [x] python -m uvicorn (PATH-safe)
- [x] View Template button (disabled during generation)
- [x] PDF download button
