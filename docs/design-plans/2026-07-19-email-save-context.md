# Save Email Context — link a sent email to the career tracker

**Status:** Shipped
**Date:** 2026-07-19

## Context

User wanted the Email Generator to persist context once they're happy with
a drafted email: who it went to, when, for what role — and if the job post
mentioned technologies/topics, feed those into a "to be learned" checklist
and a topic-frequency map. Also asked about the separate case where they
just want to tailor the resume off the same job post, without necessarily
sending an email.

The career module already had most of the needed shape: `interview_topics`
(per-company checklist, `covered` flag) is exactly the "to-learn checklist,"
and `jd_keyword_observations` (fed by `career/topic_mapping.log_keywords`,
already hooked into the main pipeline's recruiter step) is exactly the
topic map. Neither was wired to the Email Generator, and email drafts
(`_emails` dict in `api.py`) were in-memory only — nothing survived a
server restart.

## Decisions (via user Q&A)

- **Storage:** new `sent_emails` table, linked to `apply_later` via
  `apply_later_id`, rather than bolting email columns directly onto
  `apply_later`. Keeps `apply_later`'s schema a tracker, not a mailbox.
- **Topic extraction:** every save auto-adds every extracted keyword to
  both the topic map and that company's checklist, no confirmation step —
  accepted the noise trade-off (checklist grows with every required/
  preferred keyword across every saved email) in exchange for zero friction.
- **Resume tailoring link:** a manual "Tailor Resume for This Role" button,
  not automatic. Reuses the existing Generator tab pipeline instead of a
  second, duplicated pipeline UI inside the email generator.

## Backend

- `career/db.py`: new `sent_emails` table (`id, resume_id, apply_later_id,
  company_name, role_title, to_addr, subject, body, source_url, sent_at`).
- `agents/email_generator.py`: `_GENERATE_PROMPT` now also extracts
  `company_name` (empty string if the post never names the company).
- `career/email_link.py` (new): `save_email_context(...)` — inserts the
  `sent_emails` row; finds the most recent `apply_later` row for that
  company (case-insensitive) and sets `status='Applied'` + `date_applied`
  (only filling `date_applied` if blank), or creates one if none exists;
  calls `agents.recruiter.analyze()` on the job post (same call the main
  pipeline already makes) and reuses `topic_mapping.log_keywords()` for the
  topic map; adds any keyword not already on that company's checklist to
  `interview_topics`, deduped case-insensitively. Keyword extraction is
  wrapped in try/except (non-fatal) — a failed Claude call doesn't block
  the save.
- `api.py`: `_emails[email_id]` now also carries `company_name`, `job_post`,
  `source_url` (needed at save time). `EmailGenerateRequest` gained
  `source_url`; new `EmailSaveRequest` (`company_name`, `role_title`,
  `source_url` — all optional overrides, falling back to the stored draft
  values). New `POST /api/email/{email_id}/save`, 400s if no company name
  is available from either the request or the draft.

## Frontend (`ui/src/app/email-generator/`)

- `EmailDraft` gained `company_name`; `EmailService.save()` calls the new
  endpoint, `EmailService.generate()` now sends `source_url`.
- Preview panel: editable Company/Role fields (pre-filled from the
  generated draft, editable before saving since not every post names the
  company explicitly), a **Save** button, and a confirmation banner
  showing what got linked/created and which topics were added.
- A separate **Tailor Resume for This Role** button — `@Output()
  tailorResume` emits the pasted job post text; `App.onTailorResume()`
  sets `this.jd` and calls `setTab('generate')`. No new backend, no
  duplicated pipeline state — reuses the Generator tab as-is.

## Verification

- `ruff check src`, `ruff format --check src`, `mypy src` all clean.
- `ng lint`, `ng build` clean (pre-existing bundle/style budget warnings
  only).
- End-to-end via curl: generate → save → confirmed rows in `apply_later`,
  `interview_topics`, `jd_keyword_observations`, `sent_emails`; a second
  save for the same company updated the existing `apply_later` row
  (`apply_later_created: false`) instead of duplicating it, and didn't
  re-add already-present checklist topics.
- End-to-end via a real Playwright browser session (isolated against a
  throwaway backend on a second port sharing the same DB files, so the
  user's running dev server and real data were untouched): signup → OTP
  (dev-console hint) → PIN setup → Email Generator → generate → Save
  (banner + chips rendered correctly) → Tailor Resume handoff (Generator
  tab's JD box correctly pre-filled). All test rows and the throwaway
  account were deleted after verification.

## Explicitly not doing (this round)

- No dedicated list view for `sent_emails` — the linked `apply_later` row
  is the only visible trace of a saved email today.
- No confirmation/picker step before keywords land on the checklist (see
  "Topic extraction" decision above) — could revisit if the checklist
  gets too noisy in practice.
