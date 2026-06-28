# TexTailor — Issue Log

---

## Issue #1 — Misplaced alignment tab character `&` in LaTeX output
**Date:** 2026-06-28  
**Severity:** Critical (pipeline crash)  
**Status:** Fixed

**Symptom:**  
`pdflatex failed. Error: ! Misplaced alignment tab character &.`  
Pipeline step 4 (Compile PDF) failed. Log pointed to `P&L` inside `\bulletitem{}` on lines 206 and 209 of the tailored output.

**Root cause (3 layers):**  
1. `resume/main.tex` contained two unescaped `P&L` strings in bullet items — `&` is a table-column separator in LaTeX and is illegal in text mode unless written as `\&`.  
2. The rewriter agent prompt had no escaping rule for `&`, so it could re-introduce bare `&` when weaving in keywords from JDs that mention "P&L".  
3. No post-processing safety net existed in the pipeline.

**Fixes applied:**  
- `resume/main.tex` lines 206 & 209: `P&L` → `P\&L` directly in source  
- `src/agents/rewriter.py` prompt: added rule 8 — `& → \& (P\&L not P&L), % → \%, # → \#`  
- `src/agents/rewriter.py` `_parse_output()`: added `_escape_ampersands()` post-processing using `(?<!\\)&` regex — catches any `&` the model misses without double-escaping already-correct `\&`

---

## Issue #2 — Parser + Patcher used `\header{}` but resume uses `\section{}`
**Date:** 2026-06-28  
**Severity:** Critical (silent — pipeline ran but produced unmodified resume)  
**Status:** Fixed

**Symptom:**  
Pipeline reported steps complete and a PDF was produced, but the "tailored" resume was identical to the original — no keywords were woven in and no sections were rewritten.

**Root cause:**  
`latex_parser.py` extracted sections using the regex `\\header\{([^}]+)\}` and `latex_patcher.py` replaced sections using the same `\header{Name}` pattern. The actual resume (`resume/main.tex`) uses `\section*{Professional Summary}`, `\section{Experience}`, etc. — no `\header{}` macro exists. So `extract_sections()` returned an empty dict, the rewriter received nothing to rewrite, and the patcher had nothing to patch.

**Fixes applied:**  
- `src/latex_parser.py` `extract_profile()`: pattern changed to `\\section\*?\{` instead of `\\header\{`  
- `src/latex_parser.py` `extract_sections()`: pattern changed to `\\section\*?\{([^}]+)\}(.*?)(?=\\section\*?\{|\\end\{document\})`  
- `src/latex_patcher.py` `patch()`: header_pattern changed to `\\section\*?\{Name\}` to match actual section markers

**Verified:**  
Running `python -c "from src.latex_parser import parse_resume; d = parse_resume(); print(list(d['sections'].keys()))"` now returns `['Professional Summary', 'Technical Skills', 'Experience', 'Education']`.

---

## Issue #3 — ATS score always 0.0% even after pipeline succeeds
**Date:** 2026-06-28  
**Severity:** High (feature broken — report, boost, and chat all depend on correct score)  
**Status:** Fixed

**Symptom:**  
ATS report shows 0.0% for both required and preferred keywords, even though the resume clearly contains the skills (e.g. "Generative AI", "Machine Learning" are in Technical Skills section).

**Root cause (2 layers):**  
1. `config.json` had wrong section names: `["Career Objective", "Experience", "Projects", "Skills"]`. Actual sections in `main.tex` are `["Professional Summary", "Technical Skills", "Experience", "Education"]`. Only "Experience" matched, so only Experience was rewritten.  
2. `src/api.py` pipeline step 5 scored only against `rewritten_plain` — the text of the rewritten sections. Keywords that live in Technical Skills or Professional Summary were never included in the scored text, so nothing matched.

**Fixes applied:**  
- `config.json`: `sections_to_rewrite` corrected to `["Professional Summary", "Technical Skills", "Experience"]`  
- `src/api.py` step 5: replaced `"\n".join(strip_latex(c) for c in rewritten.values())` with `strip_latex(patch_tex(resume_data["raw_tex"], rewritten, resume_data["sections"]))` — scores the full patched resume, not just the rewritten excerpts  
- `src/api.py` boost endpoint: same scoring fix applied  
- Added `from latex_patcher import patch as patch_tex` to imports

---

## Issue #4 — Template Preview iframe shows blank (white) page
**Date:** 2026-06-28  
**Severity:** Medium (feature non-functional)  
**Status:** Fixed

**Symptom:**  
Clicking "View Template" in the header opened the iframe but showed a completely white/empty frame.

**Root cause (2 layers):**  
1. All `FileResponse` endpoints in `src/api.py` passed `filename="..."` which causes FastAPI/Starlette to set `Content-Disposition: attachment`. Modern browsers (Chrome/Edge) refuse to render `attachment` responses inline inside an iframe — they either download the file silently or show a blank frame.  
2. The template endpoint only recompiled `main.pdf` if the file was missing. Since `main.pdf` existed (from before the new KGISL projects were added), the stale old PDF was served — showing a different/older version of the resume.

**Fixes applied:**  
- All `FileResponse` calls in `src/api.py` now use `headers={"Content-Disposition": "inline"}` instead of `filename="..."` — browser renders PDF in iframe  
- Template endpoint now checks `tex.stat().st_mtime > pdf.stat().st_mtime`: if `main.tex` is newer than `main.pdf`, it recompiles before serving  
- `/api/pdf/{task_id}`, `/api/chat/pdf/{edit_id}`, `/api/template` all updated

---

## Issue #5 — Resume PDF auto-downloaded instead of displaying inline
**Date:** 2026-06-28  
**Severity:** Medium  
**Status:** Fixed

**Symptom:**  
In some browser configurations, the generated PDF triggered a file download dialog instead of loading inside the iframe on the right panel.

**Root cause:**  
Same as Issue #4 — `Content-Disposition: attachment` header from `FileResponse(filename=...)`.

**Fix:** Same fix as Issue #4. The Download button remains functional because it uses `<a href="..." download="resume.pdf">` which forces a save-to-disk download independently of the server header.

---

## Issue #6 — PDF font rendering not crisp
**Date:** 2026-06-28  
**Severity:** Low  
**Status:** Fixed

**Symptom:**  
Text in the PDF appeared slightly blocky or bitmap-like rather than smooth vector text, especially at certain zoom levels.

**Root cause:**  
`lmodern` + T1 encoding produces vector fonts, but without `microtype` the character spacing and glyph placement are not optimised for screen rendering.

**Fix:**  
Added `\usepackage[protrusion=true,expansion=true,final]{microtype}` to `resume/main.tex` preamble. Microtype enables character protrusion (glyphs extend slightly into margins for optical alignment) and font expansion (subtle glyph width adjustments for even spacing) — produces visibly sharper output.

---

## Issue #7 — Duplicate "Generate Resume" label (tab + action button)
**Date:** 2026-06-28  
**Severity:** Low UX  
**Status:** Fixed

**Symptom:**  
The tab navigation showed "Generate Resume" and the submit button inside the left panel also said "Generate Resume". Users reported seeing two identical labels and being unsure which one to click.

**Fix:**  
- Tab labels renamed: "Generate Resume" → **Generator**, "Edit Resume" → **Resume Editor**  
- Action button renamed: "Generate Resume" → **Tailor My Resume**  
- These three labels are now visually and semantically distinct.

---

## Issue #8 — Edit Resume tab stuck on "Loading resume content…" with no feedback
**Date:** 2026-06-28  
**Severity:** Medium UX  
**Status:** Fixed

**Symptom:**  
Clicking "Resume Editor" tab showed only a spinner with "Loading resume content…" for 30–60 seconds on first open. Users assumed the app was broken and left the tab.

**Root cause:**  
First call to `GET /api/resume-md` triggers `tex_to_md()` which calls Claude to convert the full LaTeX resume to Markdown. This takes 30–60 s. The UI showed no context explaining this.

**Fixes applied (UI only):**  
- Replaced generic spinner with an animated **loading skeleton** (shimmer lines resembling text content)  
- Added explanatory text: *"First time: Claude is converting your LaTeX to Markdown (~30–60 s). Subsequent opens are instant."*  
- Actions sidebar also shows a skeleton of the Save/Discard buttons while loading  
- Syncing state shows the 3-step process: Convert MD → LaTeX, stitch preamble, compile PDF

---

## Issue #9 — Editor buttons disabled after content loads with no explanation
**Date:** 2026-06-28  
**Severity:** Low UX  
**Status:** Fixed

**Symptom:**  
After the Resume Editor loaded, both "Save Draft" and "Discard Changes" buttons were greyed out. Users thought the feature was broken.

**Root cause:**  
Both buttons have `[disabled]="!mdDirty"`. Immediately after load, `mdContent === mdOriginal` so `mdDirty = false`. The buttons are correctly disabled (nothing to save) but there was no hint explaining this.

**Fix:**  
Added `<p class="action-hint-small" *ngIf="!mdDirty && editorState === 'editing'">Make edits above to enable save.</p>` below the Save Draft button — appears only when content is loaded but unchanged.

---

## Issue #10 — Chat editor and Boost button appeared missing
**Date:** 2026-06-28  
**Severity:** High perceived (both features were implemented but not visible)  
**Status:** Fixed (root cause was Issues #3 and #4)

**Symptom:**  
Users reported Chat editor and Boost to 90%+ button were not present in the UI.

**Root cause:**  
- **Chat editor** is conditional on `activePdfUrl` being set. Because `Content-Disposition: attachment` caused the PDF to download rather than display in the iframe, `pdfUrl` was never reliably set in some browsers.  
- **Boost button** is inside the report panel which is conditional on `reportData` being populated. Because ATS scoring returned 0.0% (Issue #3), the report data was incorrect and the boost banner only shows when `overall_score < 90` — which requires the score to be a real value, not 0.0 from a broken scorer.  
- Additionally, a "Chat editor and Boost appear here after generating a resume." placeholder hint was missing when no PDF was loaded.

**Fixes applied:**  
- Issue #3 fix (correct ATS scoring) ensures the report populates correctly  
- Issue #4 fix (inline Content-Disposition) ensures `pdfUrl` is set and `activePdfUrl` becomes non-null  
- Added `.chat-unavailable` hint in the PDF panel: *"Chat editor and Boost appear here after generating a resume."*

---

## Issue #11 — Loading overlay missing during PDF generation
**Date:** 2026-06-28  
**Severity:** Low UX  
**Status:** Fixed

**Symptom:**  
While the pipeline ran (45–90 s), the PDF panel showed only the empty placeholder. No indication that something was being generated for the right-hand panel.

**Fix:**  
Added a full-panel generating overlay inside `.pdf-frame-wrap` (shown when `isGenerating && !activePdfUrl`):  
- Large animated spinner  
- Label: *"AI is tailoring your resume…"*  
- Sub-label: *"Reading your LaTeX → analysing JD → rewriting sections → compiling PDF"*  
- Time estimate: *"This usually takes 45–90 seconds"*
