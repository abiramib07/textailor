# Mandatory Application Tracking + Resume-Content-in-Interview-Prep

Status: Shipped

## Revisions after design review

A Plan-agent second-opinion review (same pattern used for the parallel
section-rewrite feature) found 7 issues before implementation started.
Addressed here:

1. **Chat-panel edits are invisible to `resume_snapshot` (and always were
   to `pdf_path`).** `POST /api/chat/execute` patches the resume
   identity's *base* `.tex` directly — a different file from
   `task["tex_path"]` (the pipeline's per-task tailored copy, written to
   its own `{job_title}_{date}` output dir). `resume_snapshot` will
   reflect the pipeline/Weave-in/Add-to-Skills output only, same as the
   pre-existing `pdf_path` already does — **not a new inconsistency**,
   just inheriting one that predates this feature. Not fixing the
   chat/task decoupling here — that's a separate, larger architectural
   change (making `chat_execute` task-aware) and out of scope for what
   was asked. Documented as a known limitation instead of silently
   ignored.
2. **`historySaved` / `saveResult` must reset when content changes after
   a save**, or the "unskippable" gate silently stops gating. Fix: reset
   `historySaved = false` in `boostAts()`'s and `addSkillsToResume()`'s
   success handlers (both mutate `task["tex_path"]`/`["pdf_path"]`, so a
   re-save would produce genuinely different content). Chat
   execute/undo/rescore are *not* included in this reset — per point 1,
   they never touch `task["tex_path"]`, so nothing about the
   task-scoped snapshot actually changes when they run. Email Generator:
   reset `saveResult = null` in `sendChat()`, `undo()`, and `saveEdit()`
   success handlers — all three mutate `draft` after a save.
3. **Interview Prep's company list must include companies from
   `resume_history`, not just `interview_topics`.** A JD yielding zero
   extractable keywords produces a history row but no checklist row, so
   that company would otherwise never appear in the sidebar. Fix:
   `interview-prep.ts` also fetches history (already needed for the
   "Resumes used" panel) and unions company names client-side —
   `interview_topics` and `resume_history` live in separate SQLite files
   (`career.db` vs `history.db`), so this union happens in the frontend,
   not via a cross-database backend query.
4. **Apply-Later link failure needs a real success/failure signal, not
   just a log line** — this *is* the primary gap the feature closes, so
   swallowing it silently would be worse than the original bug. Fix:
   `apply_later_linked: bool` in the `/api/history` response — `true`
   whether the row was created or updated (both are success), `false`
   only if linking itself raised. Frontend shows a visible (non-blocking)
   warning only on `false`.
5. **Shared TS interfaces need the new fields.** `HistoryEntry` in
   `resume.service.ts` gains `resume_snapshot: string | null`;
   `saveHistory()`'s return type gains `apply_later_linked: boolean`.
   Listed explicitly here since it's shared by both the save-flow and
   Interview Prep changes.
6. **Auto-open happens even if the user isn't on the Generator tab when
   a task finishes** — not a bug (no duplicate-open/race; the 'done'
   branch runs once per poll chain), and the existing desktop
   notification (`notify_resume_done` in `notifier.py`) already alerts
   the user cross-tab. No new cross-tab signal added — just noting the
   form will be waiting, already open, whenever they return to the tab.
7. **`SCHEMA_TABLE` in `history.py` lists `resume_snapshot`** alongside
   the `_migrate()` ALTER TABLE path, matching how `jd_text` is handled
   in both places already, not just the migration.

## Problem

The user tailors a different resume per company, applies via either the
Generator tab or the Email Generator tab, and wants two things that don't
exist today:

1. **A reliable track of every job applied to.** Saving is currently
   optional and easy to skip in both tabs, and — worse — the Generator's
   "Save to History" doesn't create/update an Application Tracker
   (`apply_later`) row at all. Only the Email Generator's "Save Email
   Context" does that (via `career/email_link.py::_link_apply_later`).
   Someone who mostly uses the Generator tab to apply currently gets no
   Application Tracker entry for that application.
2. **Quick access to exactly what resume content was sent to a given
   company**, from within Interview Prep — since interviewers ask
   questions grounded in the resume they received, and the user tailors
   a different resume per company. Today `resume_history` stores the
   compiled PDF path and the JD, but never the resume's plain-text
   content, so there's no fast way to re-read "what did I actually claim
   on the resume I sent to Company X" without opening the PDF.

## Scope

In scope:
- Close the Apply-Later linking gap on the Generator's save path.
- Store a plain-text resume snapshot on each `resume_history` row,
  captured at save time from that task's tailored `.tex`.
- Surface saved resume snapshots for the selected company inside the
  existing Interview Prep tab (no new tab).
- Make the save step in both the Generator and Email Generator
  **unskippable-but-not-blocking**: the save form is always shown (not a
  dismissible optional row) once there's something to save, and starting
  a new generation/draft while an unsaved result exists requires an
  explicit "Discard" rather than silently losing it.

Out of scope (flagged, not building now):
- A resume snapshot from the Email Generator's save path — that flow
  uses the identity's current base resume as-is (no per-JD tailoring
  happens there), so there's no new tailored content to snapshot; the
  existing Resume Editor tab already shows that content.
- A hard block on downloading/viewing the PDF before saving — the
  Generator's Weave-in/Add-to-Skills/Rescore iteration loop depends on
  being able to freely view intermediate PDFs before committing to a
  final save, and blocking that would break the core workflow for a
  requirement that's really about not *losing track* of an application,
  not about restricting iteration.

## Design

### 1. Apply-Later auto-link from `/api/history`

`career/email_link.py` gets a new public wrapper around the existing
private `_link_apply_later`:

```python
def link_apply_later(resume_id: str, company_name: str, role_title: str, source_url: str) -> tuple[str | None, bool]:
    """Create or update this company's Apply Later row (status → Applied).
    Public entry point for callers outside this module — e.g. the
    Generator's Save to History, which needs the same linking behavior
    `save_email_context` already gives the Email Generator's save path."""
```

`api.py::save_history` calls it (non-fatal, same try/except pattern
already used there for `add_checklist_topics`) and returns
`apply_later_created: bool` alongside `entry`/`topics_added` so the
frontend can show one consistent confirmation banner.

### 2. Resume snapshot on `resume_history`

`history.py`:
- New nullable column `resume_snapshot TEXT`, added via the existing
  `_migrate()` ALTER-TABLE pattern (same as how `jd_text` was added).
- `save_entry()` gains a `resume_snapshot: str` parameter, stored as-is.

`api.py::save_history`: computes the snapshot the same way
`/api/compare` and `/api/pitch` already do —
`parse_resume(tailored_path)["plain_text"]`, where `tailored_path =
task.get("tex_path") or base_path` — never a raw `strip_latex()` over the
whole file (that path still includes the LaTeX preamble; established as
the wrong pattern in the 2026-08-09 `strip_latex()` bug fix and in the
Diff Viewer/ATS Verifier design docs).

Old rows keep `resume_snapshot = NULL` — no backfill attempted (the
original tex isn't recoverable after the fact); the UI shows "No saved
content for this entry" for those.

### 3. Interview Prep: resumes used, per company

`InterviewPrepComponent` already scopes everything by
`selectedCompany`. Add:
- Inject `ResumeService`, call `getHistory()` once per resume-identity
  change (mirrors how `topics`/`companies` already reload on identity
  change), filter client-side by
  `entry.company_name.toLowerCase() === selectedCompany.toLowerCase()`.
  Client-side filtering (not a new backend endpoint) because a single
  identity's history list is small and this avoids adding a redundant
  `company_name` query param to `/api/history` for a one-tab, low-volume
  filter.
- New "Resumes used" section above or alongside the topic checklist:
  one row per matching history entry (role title, score, applied date),
  each with a "View resume content" toggle that expands the plain-text
  `resume_snapshot` (monospace, read-only, copy button — same visual
  language as the Personal Info clipboard fields) or, if `null`, the
  "No saved content for this entry" fallback line.

### 4. Unskippable (not blocking) save UX

**Generator (`app.ts`/`app.html`)**:
- Replace the current two-step "optional row → click → form opens" with
  the save form auto-opening as soon as `status.status === 'done'`.
- `generate()` (starting a *new* tailoring run): if the previous
  completed task exists and `!historySaved`, don't silently wipe it —
  show an inline confirm ("You have an unsaved application above — Save
  it first, or Discard & Continue") before proceeding.  Only two exits:
  save, or explicit discard.

**Email Generator (`email-generator.ts`/`.html`)**:
- Same pattern: `save()` stays the action, but `newEmail()` (and
  starting a new `generate()` while `draft` exists and `!saveResult`)
  gets the same "Save it first, or Discard & Continue" confirm instead
  of silently clearing the unsaved draft.

Neither change blocks PDF viewing, Weave-in, Rescore, chat edits, or
Send Email — those all keep working exactly as they do today. The only
new friction is at the two "I'm about to move on and could lose track
of this application" moments: starting fresh, or leaving the tab.

## Data model changes

```sql
ALTER TABLE resume_history ADD COLUMN resume_snapshot TEXT;  -- nullable, plain text
```

No other schema changes — `apply_later` and `interview_topics` already
have everything needed.

## API changes

- `POST /api/history` — response gains `apply_later_linked: bool` (`true`
  whether the Apply Later row was created or updated; `false` only if
  linking itself raised — see revision 4 above). Existing
  `entry`/`topics_added` unchanged. `entry` now also includes
  `resume_snapshot` (it's a column, so it flows through the existing
  `dict(row)` return automatically).
- No other endpoint signature changes. `GET /api/history` needs no
  changes — it already returns full rows.

## Test plan

Backend (`pytest`, written before implementation, confirmed failing
first):
- `history.py`: migration adds `resume_snapshot` to a pre-existing DB
  without the column; `save_entry`/`get_entry`/`list_entries` round-trip
  the new field; NULL is preserved for rows that don't set it.
- `career/email_link.py`: `link_apply_later` creates a new Apply Later
  row when none exists for that company, and updates an existing one to
  `status='Applied'` (mirrors the existing `_link_apply_later` behavior,
  just via the new public entry point).
- `api.py::save_history`: a completed task saved via `/api/history`
  produces (a) a `resume_snapshot` equal to
  `parse_resume(tailored_path)["plain_text"]`, not a raw/preamble-including
  string, and (b) `apply_later_created=True` plus a real `apply_later`
  row on first save for that company, and `apply_later_created=False`
  with the existing row updated on a second save for the same company.

Frontend: no existing spec/unit-test runner in this repo (this project's
automated tests are pytest-only per the 2026-08-09 worklog entry); `ng
lint` / `ng build` clean plus a live smoke test is the established
verification pattern here, so that's what's used for the UI changes.

## Open assumptions (flag before/while implementing)

- "Mandatory" is implemented as *unskippable-but-discardable* (always
  shown, confirm-to-discard) rather than a hard block on other actions.
  Rationale in "Out of scope" above — a true hard block would prevent
  the Weave-in/Rescore iteration loop the app depends on. If a genuinely
  hard block turns out to be what's wanted, that's a follow-up UX change
  on top of this, not a reason to block this design.
- Resume-content-in-Interview-Prep is scoped to Generator-tailored
  resumes only (see "Out of scope"), since that's the flow the user
  described tailoring per company.
