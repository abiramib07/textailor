# ATS Score Verifier — independent resume+JD rescan

**Status:** Shipped
**Date:** 2026-08-09

## Context

After Weave-in/Add-to-Skills boosts push the score up (e.g. to 100%), the
displayed number comes from re-scoring the *in-memory* task state
(`recruiter_result` + the freshly patched text). User wants an independent
sanity check: attach the resume file fresh and paste the JD again, run a
clean scan from scratch, and confirm the same score holds up — decoupled
from any task/session state, the same way diffchecker-style "verify"
workflows work.

This is a legitimate concern: the in-memory score has never been
cross-checked against a fully independent parse of the file the way an
external ATS would see it.

## Decisions (confirmed via user review)

1. **Placement:** inline in the Generator tab's result panel — a "Verify
   Score Independently" button next to the score. Rather than trying to
   pre-populate the native file `<input>` with the current PDF (browsers
   don't allow assigning a File to an input's FileList except via the
   `DataTransfer` workaround, which is unnecessary complexity here), the
   panel defaults to **re-reading the current task's tex file server-side**
   when no file is attached (pass `task_id`, no upload needed — still a
   genuinely fresh `recruiter.analyze()` call, not reusing the cached
   `recruiter_result`), and switches to using an uploaded file instead the
   moment the user attaches one. The JD textarea pre-fills from the
   component's existing `jd` field (already in memory, trivial). This
   keeps the feature in context of the score being questioned without
   fighting browser file-input APIs.
2. **Ephemeral, not persisted:** the uploaded file is extracted to plain
   text, scored, and discarded — nothing written to `resumes.db` or
   `resume/`.
3. **Supported file types:** reuse `resume_importer.extract_text()` as-is
   (PDF, DOCX, TXT, MD) plus a `.tex` → `strip_latex()` path for LaTeX
   uploads — matches what Import Resume already accepts, no new parsing
   code needed.

## Planned backend (`src/`)

- New `POST /api/ats-check` (multipart form: `jd: str` required, `file:
  UploadFile | None`, `task_id: str | None`) in `api.py`. Exactly one of
  `file`/`task_id` must resolve to text: if `file` is attached, extract
  plain text from it (`resume_importer.extract_text()` for pdf/docx/txt/md;
  decode + `strip_latex()` for `.tex`); else if `task_id` is given, read
  that task's current tex path fresh off disk and `strip_latex()` it. Then
  runs the existing `agents.recruiter.analyze(jd, text)` →
  `agents.ats_scorer.score(...)` pipeline — the same two calls the main
  pipeline already makes, against fresh input, with no rewrite/compile
  step, so it's fast (one Claude call, not five — and critically, a *new*
  `analyze()` call rather than reusing the cached `recruiter_result`, so
  this also catches drift/non-determinism in the keyword extraction
  itself, not just re-scoring). Returns the same `ScoreReport` shape
  `/api/report/{task_id}` already returns, so the frontend can reuse the
  existing report-rendering markup.
- No new agent file needed — this is pure reuse/composition of
  `recruiter.analyze` + `ats_scorer.score`, no new prompt.

## Planned frontend

- Inline panel in `app.html`/`app.ts` (Generator tab result section, not a
  new routed component — small enough to stay co-located with the score
  card it's verifying): file input (optional) + JD textarea (pre-filled
  from `this.jd`) + "Scan" button → calls a new `resume.service.ts` method
  `atsCheck(jd, taskId, file?)` → renders the result using the same
  keyword-cloud / score-card markup already used for the main report.
- Shows the verified score next to (not replacing) the pipeline's own
  score, so the user can visually compare the two numbers.

## Verification plan

- `ruff check src`, `ruff format`, `mypy src` clean.
- `ng lint`, `ng build` clean.
- Backend pytest: `resume_importer.extract_text()` already has no test
  coverage — add unit tests for pdf/docx/txt/md extraction using small
  fixture files, plus a test that `.tex` input goes through `strip_latex()`
  correctly. Mock `agents.recruiter.analyze`/`ats_scorer.score` (both pure
  functions once given text) to test `/api/ats-check`'s request handling
  (400 on unsupported extension, 400 on empty file) without a real Claude
  call.
- Live smoke test: upload the actual current tailored PDF + the same JD
  used to generate it, confirm the returned score is in the same ballpark
  as the pipeline's own reported score (not necessarily identical — a
  fresh PDF text extraction can differ slightly from the LaTeX-source
  `strip_latex()` text the pipeline scores against — see caveat below).

## Known caveat to flag to the user

Scoring a PDF-extracted text and scoring the original `strip_latex()` text
are not guaranteed to produce identical percentages, since PDF text
extraction (via `pypdf`) can merge/reorder text in ways `strip_latex()`
doesn't. A small delta between the two numbers is expected and doesn't
necessarily mean the pipeline's score was wrong — this should be surfaced
in the UI copy so it doesn't itself look like a new bug.

## Explicitly not doing (this round)

- Not persisting verification results anywhere (no history/tracker entry).
- Not blocking/gating the pipeline's own score on this — purely an
  optional, on-demand second opinion.

## Important addendum: this feature is what surfaced a critical pre-existing bug

While writing test fixtures for this feature, discovered that `strip_latex()`
(`src/latex_parser.py`) was silently deleting the entire content of this
template's structural macros — `\bulletitem`, `\bulletpoints`, `\techline`,
`\projectheading`, plus the role-title arg of `\jobheading` — and truncating
any line containing an escaped `\%` at the first occurrence. This meant the
recruiter/scorer agents had been operating on a resume representation
missing nearly all bullet content, tech-stack lines, and project/job titles
— i.e. every ATS score shown by this app before this fix was computed
against a gutted version of the resume. Full RCA, fix, and regression tests
in `tests/test_latex_parser.py` — see `WORKLOG.md` 2026-08-09 for the
complete writeup. This was fixed *before* shipping the Verifier itself,
since the Verifier would otherwise have immediately surfaced a large,
confusing score discrepancy against the (then-still-broken) pipeline score,
rather than the expected small PDF-extraction-vs-source delta described in
the caveat above.

## Shipped

- `POST /api/ats-check` in `api.py`, exactly matching the planned shape
  (`jd` required, `file` optional, `task_id` optional fallback).
- Inline panel in `app.html`/`app.ts` (Generator tab) — JD textarea
  pre-filled from the active `jd`, optional file attach, "Scan" button,
  result shown as a small green summary card next to the pipeline's own
  score.
- `resume.service.ts` gained `atsCheck(jd, taskId, file?)`.
- Verified: `ruff`/`mypy`/`ng lint`/`ng build` all clean; 7 pytest cases in
  `tests/test_api_verify_features.py::TestAtsCheckEndpoint` cover missing
  JD, missing file-or-task_id, empty file upload, a real `.txt` upload
  scored via a genuinely fresh (non-cached) `analyze()` call, a `.tex`
  upload routed through `strip_latex()`, the `task_id` fallback path, and
  an unknown `task_id` with no file. Live smoke test against a real
  `/api/generate` run: same preamble-noise bug as the Diff Viewer's
  endpoint, found in the `task_id` fallback path and fixed the same way;
  after the fix, both the `task_id` path and a genuine PDF file upload
  (downloaded the task's real compiled PDF, re-uploaded it) independently
  returned a clean 100% / "Ready to submit" against the same JD, all 8
  required keywords found either way — end-to-end confirmation that a
  fresh upload and the pipeline's own resume agree.
