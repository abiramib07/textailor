# Send Email — one-click send with resume attached

**Status:** Shipped
**Date:** 2026-07-26

## Context

User wants a **Send Email** button in the Email Generator that sends the
drafted email as-is, with the correct subject, to a real recipient address,
with the current resume attached as a PDF — fully automated, not just a
copy/download step.

Two things ruled out the obvious approach (using the Gmail connection the
user already made to Claude):

- That connection is scoped to this Claude Code **chat session**, not to
  the TexTailor backend. A button click in the Angular UI hits `api.py`
  over HTTP — it has no path into Claude's own MCP connectors. Automation
  has to be a first-party integration in the backend, independent of it.
- Even in-chat, the Gmail tools available (`create_draft`/`update_draft`)
  have no "send" action at all (draft-only, human clicks Send in Gmail),
  and `create_draft` explicitly doesn't support attachments yet. So the
  connector couldn't do this even if the backend could reach it.

Token cost: none beyond what's already spent generating/revising the
draft. Sending is a plain network call (SMTP), not a Claude call.

## Decisions (via user Q&A)

- **Transport:** SMTP with a Gmail App Password (`smtplib` +
  `email.mime.multipart`), not Gmail API/OAuth. Matches the size of a
  single-user local tool — no Google Cloud project, no OAuth consent
  screen, no refresh-token storage. One-time setup: enable 2FA on the
  sending Gmail account, generate a 16-char app password, store it as a
  secret (env var, not committed).
- **Recipient:** new editable **Send to** field, validated as an email
  address, required before Send is enabled. The AI-drafted `to` field is
  often a placeholder ("Hiring Manager") since job posts rarely include an
  address — can't be trusted as the real recipient.
- **Attachment:** compile the resume tied to this draft fresh at send-time
  (`compile_tex(tex_path)`, same call the existing download/compile paths
  already make) rather than attaching a pre-tailored PDF. Simpler, always
  current. Attaching the ATS-tailored version for this specific role is a
  possible follow-up but needs the email draft linked to a tailoring
  `task_id`, which doesn't exist today (Generator and Email Generator are
  only loosely connected via the existing "Tailor Resume for This Role"
  button).
- **Safety:** a confirm step before the actual send — shows To, Subject,
  and the attachment filename, requires a click to proceed. Sending is
  irreversible (unlike Save, which only writes to the local tracker), so
  no silent one-click send.

## Planned backend (`src/`)

- New secret: `GMAIL_SENDER_ADDRESS` + `GMAIL_APP_PASSWORD` (env vars,
  documented in whatever the project's local `.env`/setup doc is — not
  committed).
- New module `src/agents/email_sender.py` (not an LLM agent despite the
  folder — no Claude call involved, but it's the natural home next to
  `email_generator.py` for anything touching the same `_emails` draft
  shape): builds a `MIMEMultipart` message (plain-text body, PDF
  attachment via `MIMEApplication`), sends over `smtplib.SMTP_SSL` to
  `smtp.gmail.com:465`.
- `api.py`: new `EmailSendRequest` (`to: str`, required) and
  `POST /api/email/{email_id}/send`. Validates `to` is non-empty and
  looks like an email address (reuse whatever validation pattern, if any,
  already exists in `auth/schemas.py`; otherwise a simple regex — this is
  submission-time validation, not full RFC 5322 parsing). Compiles the
  resume tied to the draft's `resume_id` via the existing `compile_tex`
  path, reads the resulting PDF bytes, calls `email_sender.send(...)`.
  On success, logs a `sent_emails`-style record (reuse `email_link` if it
  makes sense, or extend `EmailSaveRequest`'s flow — exact reuse vs. new
  path to be decided during implementation) so a sent email shows up the
  same way a saved one does. 500s with a real error detail on SMTP
  failure (auth failure, connection refused, etc.), following the
  try/except → `HTTPException` pattern already used by every other email
  endpoint (including the fix just made to `email_save`).

## Planned frontend (`ui/src/app/email-generator/`)

- New **Send to** field in the save row (next to Company/Role/Job Link),
  bound to a new `sendTo` field on the component, basic client-side email
  pattern validation before the button is enabled.
- New **Send Email** button next to the existing Save button. Click opens
  a confirm dialog (To, Subject, attachment filename) — confirming fires
  `EmailService.send(emailId, sendTo)`. Busy/error states follow the same
  pattern as `save()`/`isSaving`/`saveError`.
- Success state: banner similar to the existing save-result banner
  ("Sent to X — resume attached"), doesn't replace the Save flow (sending
  and saving to the tracker stay separate actions — user might send now,
  save later, or vice versa).

## Verification

- `ruff check src`, `ruff format --check src`, `mypy src` all clean.
- `ng lint`, `ng build` clean (pre-existing bundle/style budget warnings
  only).
- End-to-end via curl against the running dev server: generate → send with
  an invalid address (400, "Enter a valid recipient email address") →
  send with a valid address but no `GMAIL_SENDER_ADDRESS`/
  `GMAIL_APP_PASSWORD` configured yet (clean 500 with a real error
  message, confirming the resume PDF compiled successfully and only the
  missing credentials blocked the actual SMTP call) → send against a
  nonexistent `email_id` (404).
- Real SMTP send not yet exercised end-to-end — needs `GMAIL_SENDER_ADDRESS`
  and `GMAIL_APP_PASSWORD` set in `.env` (see `.env.example`), which is
  the user's one-time setup step (enable 2FA on the sending Gmail
  account, generate an app password at
  https://myaccount.google.com/apppasswords).

## Explicitly not doing (this round)

- No Gmail API/OAuth path — SMTP + app password only, per the decision
  above. Revisit only if app passwords stop working for the account in
  use.
- No attaching the ATS-tailored resume automatically — always the fresh
  base-resume compile. Linking a tailoring `task_id` to an email draft is
  a bigger change, deferred.
- No send-history list view — same gap as the existing Save feature
  (tracked in `2026-07-19-email-save-context.md`), not being solved here
  either.
- No retry/queue on SMTP failure — a failed send just surfaces the error;
  the user clicks Send again.
