# Worklog

End-of-day log, newest entry on top. Short bullets — what got done, not a
narrative. See `CLAUDE.md` → "Git hygiene".

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
