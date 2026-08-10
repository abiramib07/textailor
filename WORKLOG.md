# Worklog

End-of-day log, newest entry on top. Short bullets — what got done, not a
narrative. See `CLAUDE.md` → "Git hygiene".

## 2026-08-09
- Shipped Mandatory Application Tracking + Resume-Content-in-Interview-Prep
  (design doc: `docs/design-plans/2026-08-09-mandatory-application-tracking.md`),
  full design→review→TDD→implement→verify pass:
  - **Closed a real tracking gap**: the Generator tab's "Save to History"
    never touched the Application Tracker (`apply_later`) — only the
    Email Generator's save path did. New `career/email_link.py::
    link_apply_later()` public wrapper around the existing
    `_link_apply_later`; `api.py::save_history` now calls it and returns
    `apply_later_linked: bool` (true whether the row was created or
    updated — false only if linking itself raised, so a genuine failure
    is visible instead of silently swallowed).
  - **New `resume_snapshot` column on `resume_history`** — plain-text
    capture of the task's own tailored resume at save time
    (`parse_resume()["plain_text"]`, same pattern as `/api/compare` and
    `/api/pitch`, not a raw `strip_latex()` over the file), surfaced in
    Interview Prep's new "Resumes used" panel per company (with a
    view/copy toggle) so interview questions grounded in "what does my
    resume for Company X actually say" are answerable without opening
    the PDF. Interview Prep's company sidebar now unions companies from
    `resume_history` too, not just `interview_topics` (a JD with zero
    extractable keywords produces a history row but no checklist row,
    which would otherwise hide that company entirely).
  - **"Unskippable but discardable" save UX** in both the Generator and
    Email Generator: the save form auto-opens once a task/draft
    completes (no more dismissible "Save to history?" row you could
    just ignore), and starting a new generation/draft while the current
    one is unsaved now prompts "Save it first, or Discard & Continue"
    instead of silently clearing it. Deliberately *not* a hard block —
    PDF viewing/Weave-in/Rescore/chat edits all still work freely before
    saving; only the two "about to lose track of this" moments (starting
    fresh, leaving) gained friction. `historySaved`/`saveResult` now
    reset after Weave-in/Add-to-Skills (Generator) and chat-revise/undo/
    manual-edit (Email Generator), since those mutate the underlying
    content a stale "saved" flag would otherwise hide.
  - **Process**: wrote the design doc, sent it to a Plan-agent for a
    second-opinion review (same pattern as the parallel-rewrite feature
    below) — it found 7 real gaps before any code was written, most
    importantly that chat-panel edits are invisible to both the new
    snapshot and the pre-existing `pdf_path` (documented as a known
    limitation, not fixed — chat edits patch the base resume file, a
    different file from the task's tailored copy, and making
    `chat_execute` task-aware is a separate, larger change), that
    `historySaved`/`saveResult` needed explicit resets or the "unskippable"
    gate would silently stop gating, and that Interview Prep's company
    list needed the cross-DB union. All 7 addressed in the revised doc
    before implementation started.
  - **Tests written first** (`tests/test_mandatory_tracking.py`, 13
    cases), confirmed failing against the unmodified code, then passing
    after implementation: schema migration/round-trip for
    `resume_snapshot` (including NULL), `link_apply_later` create-vs-update
    behavior, and `save_history`'s snapshot capture (plain-text not raw,
    correct task-tex-path vs base-path fallback, non-fatal on a missing
    file) and `apply_later_linked` signal (true on create, true on
    update — not just create — false only on genuine failure). Full
    suite 68/68, ruff/ruff format/mypy clean, `ng lint`/`ng build` clean.
  - **Live smoke test** against the real running server (including a
    process cleanup after an accidental stale-server false negative —
    two overlapping `--reload` process trees left an old one bound to
    port 8000): real `/api/generate` → `/api/history` save →
    confirmed a real `apply_later` row created (status Applied), a
    second save on the same company updated it rather than duplicating
    (still 1 row), `resume_snapshot` populated with real parsed resume
    text, and `GET /api/history` surfacing it — then cleaned up all
    smoke-test rows (`resume_history`, `apply_later`, `interview_topics`)
    afterward.
  - Not done this session: a manual browser click-through of the new
    auto-opening save form, discard-confirm dialogs, and Interview Prep's
    "Resumes used" panel (no browser-automation tool available) —
    flagged as still worth a manual pass.
- Parallelized rewriter.py's per-section Claude calls (design doc:
  `docs/design-plans/2026-08-09-parallel-section-rewrite.md`) — Tailor and
  Weave-in were both taking over a minute because `rewrite()` called
  `ask_claude()` once per section *sequentially*, and each call spawns a
  fresh `claude --print` CLI subprocess with real cold-start overhead.
  Sections are independent, so they now run concurrently via
  `ThreadPoolExecutor`, with output/warning ordering reassembled back into
  `sections_to_rewrite`'s original order (not completion order) so
  behavior stays deterministic. Design review (via a Plan-agent second
  opinion) caught 3 real gaps before implementation: `max_workers=0`
  crash on empty input, nondeterministic behavior on duplicate section
  names, and a naive result-collection pattern that would've broken
  per-section exception isolation — all three addressed in the shipped
  code. 7 new tests in `tests/test_rewriter_parallel.py`, written first
  and confirmed failing against the old sequential code (concurrency
  proof + duplicate-name dedup), then passing after the change; full
  suite 55/55, ruff/mypy clean. Live smoke test against the running dev
  server confirmed both endpoints still produce clean output (no leaked
  AI commentary, scores computed correctly, valid PDFs).
- Shipped "Regenerate Pitch Material" in the Generator tab: after a resume
  finishes generating, a button drafts a JD-tailored short pitch / written
  bio / project talking points / cover letter template from that task's
  actual JD + tailored resume, previews them for editing, and saves each
  to Personal Info only on explicit confirm (never auto-overwrites).
  New `src/agents/pitch_generator.py` (Claude-backed, prompt-in/JSON-out,
  same pattern as `recruiter.py`/`email_generator.py`) + `POST
  /api/pitch/{task_id}` in `api.py` (mirrors `/api/compare`'s
  `parse_resume()["plain_text"]` pattern, not the noisier raw-strip_latex
  path `_tailored_tex_text` still uses for `/api/verify` — worth revisiting
  there too at some point). Frontend: `ResumeService.generatePitches()`,
  new state/methods in `app.ts`, preview panel in `app.html` reusing the
  existing history-save-form styling. Backend (ruff/ruff format/mypy) and
  frontend (ng lint/ng build) clean. Live smoke test: real `/api/generate`
  run against a GenAI-engineer JD, then `/api/pitch/{task_id}` — output
  correctly grounded in the resume's actual projects (QA-Bot, RAG chatbot,
  LangGraph system), JD-tailored framing, `[one specific reason tied to
  their product/mission]` placeholder preserved rather than invented.
  Manual browser click-through of the new button/preview/save flow not
  done (no browser-automation tool available this session) — flagged as
  still worth checking.
- Populated the Personal Info Clipboard's new fields (short pitch, written
  bio, project talking points, cover letter template) for the "My Resume"
  and "Abirami B" identities via direct API calls, using content drafted
  in conversation — same underlying person, safe to duplicate. Explicitly
  did NOT populate the third identity, "Raj Sabari" — confirmed via
  `main.tex` that it's a different person's resume (RAJSABARI K P, own
  email/phone), so copying Abirami-branded pitch content there would have
  been wrong; left for the user to decide (generate from Raj's actual
  resume, or leave empty).
- Competitor analysis written up:
  `docs/2026-08-09-competitor-analysis.md` — compares TexTailor against
  Jobscan/Rezi/Teal/Huntr/Four-Leaf/FastApply/JobCopilot/Kickresume.
  **Future TODO, nothing scheduled**: auto-apply/bulk-apply, named-ATS
  parser simulation (Workday/Greenhouse/Taleo/iCIMS), a Workday
  LaTeX-PDF-compatibility check (fonts-as-images is a known Workday
  parsing failure mode), a browser extension/autofill, multiple resume
  templates/DOCX export, mock interview practice, and a standalone
  cover-letter artifact. See the doc for the full gap list before
  promoting any of these to a design plan.
- Shipped Job-Site Account Credentials — new "Account Credentials" tab
  storing encrypted email/password/notes per company account, scoped to
  the active resume identity (design doc:
  `docs/design-plans/2026-08-09-job-account-credentials.md`). New standalone
  `src/credentials/` module (Fernet encryption, own SQLite DB, gated
  behind login unlike `career`/`resumes`) + `ui/src/app/career/job-credentials/`.
  13 tests written before the implementation existed, confirmed failing,
  then passing once built — caught a real bug where `_load_or_create_key`'s
  default-parameter binding made the encryption key path unpatchable in
  isolation, and a wrong test fixture assumption about which module owns
  `auth.db`'s thread-local cache. Live smoke test against the real running
  server included a full backend process kill+restart to confirm the
  persisted encryption key (not an in-memory-only one) survives restarts.
  Frontend `ng lint`/`ng build` clean; a full browser click-through of the
  new tab wasn't completed in this environment (no browser-automation tool
  available) — flagged as still worth a manual check.
- Removed the "Predictive Analytics & Cross-Dataset Insights" project and
  replaced the Professional Summary across all resume identities (default +
  "Abirami B" import), including their `resume-content.md` counterparts;
  recompiled PDFs
- Fixed a Weave-in UX bug where `confirmBoostSelection()`/
  `confirmAddToSkillsSelection()` cleared the keyword selection *before* the
  async request even started, so every selected chip snapped back to red
  the instant you clicked — looked like the click did nothing during the
  20-90s AI rewrite. Now the selection stays visible (with a pulsing
  "pending" style) until the request resolves, clears only on success, and
  is preserved on failure so a retry doesn't require reselecting everything
- Added a live elapsed-seconds counter to the Weave-in button (reusing the
  same pattern as the Generate pipeline / Email Generator), since the
  backend has no progress-streaming for this endpoint and a bare "Weaving
  in…" label with no feedback for up to a minute read as a hang
- **Found and fixed a critical, long-standing bug in `strip_latex()`**
  (`src/latex_parser.py`): the generic "delete unrecognised `\command{...}`"
  cleanup was deleting the ENTIRE content of this template's structural
  macros — `\bulletitem`, `\bulletpoints`, `\techline`, `\projectheading`,
  plus the role-title arg of `\jobheading` — instead of unwrapping them.
  Separately, comment-stripping ran before `\%`-unescaping, so any bullet
  containing a literal percent (e.g. "85\% answer relevance...") got
  truncated at the first `\%`, losing everything after it on that line.
  Net effect: the recruiter/scorer agents had been operating on a resume
  representation missing nearly all bullet content, tech-stack lines, and
  project/job titles — **every ATS score this app has ever shown was
  computed against a gutted resume**. Fixed both regexes, added 12
  regression tests (`tests/test_latex_parser.py`). Real-world confirmation:
  a live `/api/generate` run against a GenAI-engineer JD scored **90-100%
  "Ready to submit" on the first pass with 0 missing keywords** — no
  Weave-in needed at all, versus the 44.8% → multiple weave rounds seen
  earlier in the same session before the fix
- Shipped two new features (design docs:
  `docs/design-plans/2026-08-09-resume-diff-viewer.md` and
  `2026-08-09-ats-score-verifier.md`):
  - **Resume Diff Viewer** — `GET /api/compare/{task_id}` (base vs. current
    tailored, plain text) + `ResumeCompareComponent`, a side-by-side
    word-diff modal (`diff` npm package) opened via a new "Compare with
    original" button in the Generator tab
  - **ATS Score Verifier** — `POST /api/ats-check` (multipart: `jd` +
    either `file` or `task_id`), re-runs `recruiter.analyze()` +
    `ats_scorer.score()` from scratch (genuinely fresh, not the cached
    `recruiter_result`) against either an uploaded resume file or the
    task's current tex re-read off disk; inline panel in the Generator tab
    next to the pipeline's own score
  - Both endpoints initially had the same bug: running `strip_latex()` on
    the *raw* tex file (including the LaTeX preamble/macro definitions)
    instead of `parse_resume()["plain_text"]` — caught by the endpoints'
    own smoke tests, fixed, re-verified
- Backend test infra didn't exist before today — added `pytest` (now in
  `requirements.txt`), created `tests/`: 12 cases in `test_latex_parser.py`
  (the strip_latex fix) + 11 in `test_api_verify_features.py` (the two new
  endpoints), all passing; `ruff`/`ruff format`/`mypy` clean across all of
  `src`
- Live smoke tests: 3 full `/api/generate` pipeline runs against a real JD,
  plus real `/api/compare` and `/api/ats-check` calls (task_id fallback and
  a genuine re-uploaded PDF) against the resulting tasks — both new
  endpoints and the strip_latex fix confirmed working end-to-end, not just
  under pytest mocks
- Extended the Generator tab's existing "Save to History" action (it
  already captured company name + job URL) to also persist the JD text
  and auto-add its keywords to that company's interview-prep checklist —
  mirroring what "Save Email Context" already does, reusing the same
  `career.email_link.add_checklist_topics()` helper and the task's
  already-computed `recruiter_result` (no new Claude call needed):
  - `history.py`: new `jd_text` column on `resume_history` (migrated for
    pre-existing DBs), `save_entry()` gained a `jd_text` param
  - `api.py`: `POST /api/history` now accepts `jd`, passes it through, and
    (non-fatally) calls `add_checklist_topics(resume_id, company,
    required+preferred keywords)`, returning `topics_added` alongside `entry`
  - Frontend: `saveHistory()` now sends `jd` and returns `topics_added`;
    the post-save banner shows a chip row of newly-added checklist topics
    (same visual pattern as the Email Generator's save banner)
  - 7 new pytest cases (`tests/test_history_and_checklist_save.py`):
    schema migration (fresh DB has the column; a pre-existing DB without it
    gets migrated; round-trip save/fetch), and the endpoint (unknown task,
    happy path with checklist topics, no-keywords case, checklist-failure
    non-fatality) — all passing; `ruff`/`mypy`/`ng lint`/`ng build` clean
  - Live smoke test: real `/api/history` save against a completed task
    added 14 real JD keywords to a company's checklist, confirmed via
    `GET /api/career/interview-topics` — then cleaned up the smoke-test
    company's checklist rows and history entry afterward

## 2026-07-26
- Categorized "Add to Skills" / "Weave in with AI" additions instead of dumping everything into one generic "Additional Skills" row:
  - `latex_patcher.add_skills_row()` now maps each selected keyword to the best-fit existing Technical Skills category (word-boundary-safe rule matching against category themes — AI Frameworks, Generative AI / NLP, Agentic Architectures, DevOps / Cloud, Data & Vector Stores, etc.), appending to a matching row or creating a well-named new one (e.g. "Data Processing & Analysis") only when nothing fits
  - Verified against the user's exact pasted skill list — every keyword landed under the correct heading
- Removed the floating Personal Info Clipboard widget from every tab (reversing an earlier explicit request) — deleted `career/personal-info-widget/` entirely; the dedicated Career Tools → Personal Info page is untouched
- Fixed backend logging: the `"textailor"` logger had no handler of its own, so every `log.info(...)` in `api.py` was silently discarded regardless of uvicorn's `--log-level` (uvicorn only configures its own loggers, not root) — attached a real handler so execution trace actually shows up
- Diagnosed and fixed the "Weave in with AI" ATS score regression (reported: score dropping ~66% → 33%), via a live smoke test against the real Claude CLI on an isolated backend instance:
  - Frontend silently swallowed Weave-in / Add-to-Skills failures with no message — now shows a real toast (`boostError`)
  - Rewriter prompt sometimes placed `%NEEDS_METRIC` *before* the closing `}` of `\bulletitem{}`, turning the brace into a LaTeX comment and breaking `pdflatex` compilation outright — fixed the prompt wording, added an explicit correct-vs-wrong example
  - **Root cause**: Weave-in and Add-to-Skills always re-tailored from the pristine base resume instead of building on the task's own already-tailored output, silently discarding every keyword the initial `/api/generate` pass (or an earlier boost click) had already woven in — fixed by tracking each task's own `tex_path` in task state instead of guessing from directory file-existence (which could also silently pick up a stale file left over from a *different* task sharing the same job-title+date output directory — same bug also fixed in the Verifier's `_tailored_tex_text`)
  - Stopped letting the AI freely rewrite the structured Technical Skills table during Weave-in; it now goes through the same deterministic categorization path as Add-to-Skills, so it can no longer drop unrelated existing skills while restructuring
  - Added a "never remove existing keywords" rule to the rewrite prompt (defense in depth) and a regression-detection warning log (lists which previously-found keywords went missing, if any)
  - **Verified live**: two consecutive Weave-in clicks on the same task went 74.7% → 85.3% → 89.3%, cumulative, no regressions, no compile failures
- Gitignored a stray scratch verification PDF (`resume/_verify.pdf`) and deleted it
- Split the accumulated session work into 6 logical commits: `1b6a733` (resume content), `112f3ba` (tracker/job-finder/skills-seed backend), `25f4e59` (tracker/job-finder frontend), `767f804` (email send/save), `e6ed256` (Weave-in fixes + logging + categorization), `5029bb5` (worklog/gitignore housekeeping)

## Next up (2026-07-26)
- Manually click through the Generator tab in a real browser: the new boost-error toast, the categorized skills-table result after Weave-in/Add-to-Skills, and the Personal Info tab now that the floating widget is gone — everything above was only verified via curl/log trace + `ng lint`/`ng build`, not an actual browser pass (no browser automation tool available this session)
- The `out_dir` naming scheme (`{job_title}_{date}`, not keyed by `task_id`) is still shared across same-day/same-title tasks — the `tex_path` task-state fix closes the practical impact for Weave-in/Add-to-Skills/Verifier, but PDF paths and report files in that directory can still collide; consider suffixing filenames with a short task-id fragment
- Carried over from 2026-07-19, still unresolved: root-cause the `min_salary_lpa` Find Jobs failure (see below), write the design-plan addendum for the Find Jobs streaming/salary-filter rework, manually click through the Find Jobs panel in a browser

## 2026-07-19
- Shipped "Save Email Context" in the Email Generator (see `docs/design-plans/2026-07-19-email-save-context.md`):
  - `agents/email_generator.py` now extracts `company_name` alongside `role_title`
  - New `sent_emails` table + `career/email_link.py`: on Save, links/updates an Apply Later row (status Applied), runs `recruiter.analyze` on the job post, logs keywords into the topic map, and auto-adds unseen keywords to that company's interview-prep checklist
  - New `POST /api/email/{id}/save`; frontend gets editable Company/Role fields, a Save button, and a confirmation banner listing what got linked/added
  - Added a separate manual "Tailor Resume for This Role" action — hands the pasted job post to the existing Generator tab via an `@Output`, no duplicated pipeline UI
  - Verified end-to-end via curl (all 4 tables, dedup on repeat saves) and via a real Playwright browser session against an isolated throwaway backend (signup → email generation → Save → Tailor Resume handoff)

## 2026-07-18
- Fixed Add Resume modal: spinner during upload, success confirmation before close
- Created `open-project.bat` / `run-app.bat` desktop launchers; fixed broken relative-path bug in both
- Untracked 9 scratch/worklog files from git (kept locally), added git-hygiene rule to `CLAUDE.md`
- Set up `docs/design-plans/` tracker + this worklog file
- Proposed job-application-tracker design (upgrade Apply Later) — see `docs/design-plans/2026-07-18-application-tracker.md`
- Shipped the application tracker: tier/status/referral/dates/interview-round/salary fields on `apply_later`, live dashboard, grouped table UI — backend + frontend checks pass, verified end-to-end via curl
- Built standalone `job-search/job_tracker.xlsx` generator (openpyxl): web-searched 16 real current GenAI/RAG/LangGraph postings in India, dropdown status column, live COUNTIF Dashboard tab — folder gitignored, unrelated to the app itself
- Renamed "Apply Later" nav label to "Application Tracker" to match the shipped feature
- Added "Find Jobs" web-search agent to the in-app tracker (`src/agents/job_finder.py`, `POST /api/career/apply-later/search`, grounded via `claude --allowedTools WebSearch`) — reversed the earlier "no pre-fill" decision; verified live, no fabricated postings
- Reworked "Find Jobs" for a live execution trace + salary filter (per user request):
  - `claude_client.stream_claude()` — runs the CLI with `--output-format stream-json`, yields each event so callers see live progress instead of a silent multi-minute wait
  - `job_finder.stream_find_jobs()` — turns WebSearch/WebFetch tool-use events into human-readable trace lines ("Searching: …", "Reading: …"); added `min_salary_lpa` — instructs the agent to only include a posting if it finds real salary-aggregator evidence (AmbitionBox/Glassdoor/Levels.fyi/etc.) at/above the threshold, never an invented figure
  - `career/router.py` moved to the same background-thread + polling pattern `/api/generate` + `/api/status` already use (`POST .../search` starts it, `GET .../search/{task_id}` polls trace + result)
  - Frontend: live scrolling trace log + a "Min salary (LPA)" field in the Find Jobs panel
  - Backend (ruff/mypy) + frontend (ng lint/build) both clean
  - **Verified live twice**: a plain search (no salary filter, count 2-3) completed successfully both times with real trace lines and real inserted postings, confirming the streaming/trace mechanism itself works end-to-end
  - **One run with `min_salary_lpa=25` failed** after ~30 real search/fetch calls (it was thoroughly checking comp at Deutsche Bank, PwC, Northern Trust, UnitedHealth, etc.) — CLI exited nonzero with empty stderr. Error handling itself worked correctly (task cleanly went to `status: "error"`, no hang/crash, frontend would show the error banner) — root cause is unconfirmed, most likely the sheer WebFetch volume hit a usage/rate-limit ceiling for the session (this session had already done a lot of WebSearch work earlier), not necessarily a code bug
  - Was mid-way through isolating that (re-testing the plain path in a fresh call) when a transient "claude-sonnet-5 temporarily unavailable" classifier hiccup interrupted the session — inconclusive, needs a clean retry

## Next up (2026-07-19)
- Re-run the isolation test: confirm the plain Find Jobs path (no salary filter) still works after today's rework, in a fresh session with quota headroom
- Root-cause the `min_salary_lpa` heavy-search failure — if it's a real rate-limit ceiling (not a bug), consider capping WebFetch calls per search or defaulting to a smaller `count` when a salary filter is set, and surface a clearer error message than the raw CLI exit code
- Manually click through the Find Jobs panel in a real browser (trace log scrolling/spinner/disabled states, min-salary field) — only curl-verified so far, per `CLAUDE.md` this still needs an actual UI pass
- Write the `docs/design-plans/2026-07-18-application-tracker.md` addendum for the streaming/trace/salary-filter rework (only the plain "Find Jobs" addendum is written so far)
- Nothing from today is committed yet — decide when/what to commit (a lot of surface area: tracker upgrade, xlsx generator, Find Jobs agent + streaming rework)
