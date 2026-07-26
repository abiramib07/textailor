# Worklog

End-of-day log, newest entry on top. Short bullets — what got done, not a
narrative. See `CLAUDE.md` → "Git hygiene".

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
