# Job Application Tracker — upgrade Apply Later

**Status:** Proposed
**Date:** 2026-07-18

## Context

User asked whether TexTailor already has a job-application-tracker feature
(company/role/status/referral/follow-up, with an auto-calculated dashboard —
modeled on a typical "Excel tracker" prompt template). It doesn't. The
closest existing feature is **Apply Later**
(`ui/src/app/career/apply-later/`, backed by the `apply_later` table in
`src/career/db.py`), which only tracks: URL, company name, notes, and a
single applied/not-applied boolean.

## Decisions (via user Q&A)

- **Scope:** upgrade Apply Later in place — not a new parallel tab.
- **Dashboard:** live in-app computed stats only — no `.xlsx` export, no new
  dependency (`openpyxl` etc.). Stats derived from component state on every
  change, so there's no "recalculate before saving" staleness problem an
  actual spreadsheet would have.
- **Pre-fill:** none — no search/pre-fill agent. User adds rows manually.

## Backend (`src/career/`)

Extend the `apply_later` table via the existing `_add_column_if_missing`
migration helper (same pattern already used for the `resume_id` backfill),
so existing rows survive untouched:

- `tier` TEXT — e.g. Product / GCC / Services / Startup
- `role_title` TEXT
- `status` TEXT, default `'Not Applied'` — Not Applied / Applied /
  OA-Screening / Interview Scheduled / Interview Completed / Offer /
  Rejected / On Hold
- `referral` TEXT — Yes / No / Pending
- `date_applied` TEXT (ISO date)
- `next_follow_up` TEXT (ISO date)
- `interview_round` TEXT
- `salary_discussed` TEXT

The existing `applied` boolean is superseded by `status` (kept in the table
for backward compat, no longer read by the UI).

`src/career/schemas.py`: widen `ApplyLaterCreate` / `ApplyLaterUpdate` with
the new optional fields. `src/career/router.py`: extend the existing
PATCH-only-what's-provided logic to the new columns.

## Frontend (`ui/src/app/career/apply-later/`)

- Table view instead of the current simple list — columns matching the
  schema, `status` and `referral` as native `<select>` dropdowns (no new
  dependency), grouped/sortable by `tier`.
- Dashboard strip above the table: pure computed getters off the existing
  `entries` array (total, applied, in-progress, offers, rejected, by-tier
  breakdown).
- A short static hint block (weekly target suggestion, apply-easier-first
  ordering) at the top of the tab instead of a separate Legend/Tips view —
  consistent with how other Career tabs already show a one-line hint.

## Explicitly not doing

- No `.xlsx` export / `openpyxl` dependency.
- No search/pre-fill agent — could revisit later, seeding from the existing
  `job_posts` / post-archive data instead of a live web search.
