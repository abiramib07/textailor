# Resume Diff Viewer — compare base resume vs. tailored output

**Status:** Shipped
**Date:** 2026-08-09

## Context

After the Generator pipeline (and any Weave-in / Add-to-Skills boosts) produce
a tailored resume, there's no way to see *what actually changed* versus the
base resume — only the final score and PDF. User wants a diffchecker.com-style
comparison: two versions of the resume text, differences highlighted.

## Decisions (confirmed via user review)

1. **Before/after:** "before" = the pristine base resume for this identity
   (`resolve_resume(task.resume_id)`'s `tex_path`, untouched by any
   tailoring), "after" = the task's current tailored output
   (`task["tex_path"]` — already tracks the latest Weave-in/Add-to-Skills
   result, not just the initial `/api/generate` pass). The diff always
   reflects the *cumulative* effect of everything done so far on this task.
2. **Diff granularity:** plain text (reuse the existing `strip_latex()`
   utility already used for scoring) — comparing raw `\bulletitem{...}`
   markup would bury real content changes under LaTeX noise.
3. **Diff algorithm:** add the `diff` npm package (jsdiff — ~20KB, zero
   transitive deps, MIT, correct word-level diffing).
4. **Layout:** side-by-side (two scrollable panes), matching the
   diffchecker.com reference.

## Planned backend (`src/`)

- New `GET /api/compare/{task_id}` in `api.py`: resolves both tex paths from
  task state (no new agent, no Claude call — this is pure text extraction),
  reads + `strip_latex()`s each, returns `{original: str, tailored: str}`.
  404 if the task doesn't exist or hasn't completed.

## Planned frontend (`ui/src/app/resume-compare/`)

- New standalone component (own `.ts`/`.html`/`.scss`), opened from a new
  "Compare with original" button in the Generator tab's result panel
  (next to the existing PDF viewer / boost banner), once a task has a PDF.
- `resume.service.ts` gets a `compareTask(taskId)` method.
- Renders the diff via `diff.diffWords()` (or `diffLines()` — decide once we
  see real output) into two highlighted panes: red strikethrough for
  removed, green for added, plain for unchanged.

## Verification plan

- `ruff check src`, `ruff format`, `mypy src` clean.
- `ng lint`, `ng build` clean.
- Backend: curl `/api/compare/{task_id}` for a real completed task — confirm
  both fields present, `tailored` differs from `original` after a boost.
- Frontend: manual browser pass — generate, boost, open Compare, confirm
  highlighted additions match the actually-woven-in keywords.
- Backend pytest: mock-free unit test for the endpoint's path-resolution
  logic (right tex files picked for a given task) using a temp directory,
  since this is pure file I/O with no LLM call to mock.

## Explicitly not doing (this round)

- No PDF-level (visual) diff — text only.
- No diff history / multiple snapshots — always compares against the
  current on-disk state at request time.
- No diffing between two arbitrary resume identities — only base-vs-tailored
  for one task.

## Shipped

- `GET /api/compare/{task_id}` in `api.py` — resolves base + tailored tex
  paths from task state, `strip_latex()`s each, returns
  `{original, tailored}`. 400 if the task isn't done, 404 if a resolved tex
  path is missing on disk.
- `ResumeCompareComponent` (`ui/src/app/resume-compare/`) — modal opened via
  a new "Compare with original" button in the Generator tab's result panel,
  word-diffed with `diff.diffWords()`, rendered as two highlighted panes
  (red strikethrough = removed, green = added).
- `resume.service.ts` gained `compareTask(taskId)` and the `CompareResult`
  type.
- Verified: `ruff`/`mypy`/`ng lint`/`ng build` all clean; 4 pytest cases in
  `tests/test_api_verify_features.py::TestCompareEndpoint` cover the happy
  path, the no-tailored-output-yet fallback, an unknown task (400), and a
  missing file on disk (404). Live smoke test against 3 real
  `/api/generate` runs — first pass caught a real bug (the endpoint was
  running `strip_latex()` on the raw file, including the LaTeX preamble/
  macro definitions, instead of `parse_resume()["plain_text"]` — fixed,
  re-tested, confirmed clean: 5391 vs. 5550 chars, genuinely differing,
  zero preamble noise).

This shipped alongside the `strip_latex()` content-loss fix discovered
while building the ATS Score Verifier (see that design doc + `WORKLOG.md`
2026-08-09) — the diff viewer's `original`/`tailored` text is only
meaningful now that bullets/techlines/project titles actually survive
`strip_latex()`.
