# Design Plan Tracker

One row per feature design. Status moves Proposed → Approved → In Progress →
Shipped (or Shelved). Update the row in place — don't rewrite this file as
prose. See `CLAUDE.md` → "Git hygiene" for when to add an entry here.

| Date | Feature | Status | File |
|---|---|---|---|
| 2026-06-20 | Core 4-agent tailoring pipeline (Diagnoser → Recruiter → Rewriter → Scorer) | Shipped | [../../design_plan.md](../../design_plan.md) |
| 2026-07-18 | Job application tracker (Apply Later upgrade: tiers, status pipeline, referral, dashboard) | Shipped | [2026-07-18-application-tracker.md](2026-07-18-application-tracker.md) |
| 2026-07-19 | Save Email Context (link sent emails to Apply Later, topic map, interview checklist) | Shipped | [2026-07-19-email-save-context.md](2026-07-19-email-save-context.md) |
| 2026-07-26 | Send Email (SMTP send with resume attached, one-click from Email Generator) | Shipped | [2026-07-26-send-email.md](2026-07-26-send-email.md) |
| 2026-08-09 | Resume Diff Viewer (base vs. tailored, diffchecker-style) | Proposed | [2026-08-09-resume-diff-viewer.md](2026-08-09-resume-diff-viewer.md) |
| 2026-08-09 | ATS Score Verifier (independent resume+JD rescan) | Proposed | [2026-08-09-ats-score-verifier.md](2026-08-09-ats-score-verifier.md) |
| 2026-08-09 | Job-Site Account Credentials (encrypted email/password store per company account) | Shipped | [2026-08-09-job-account-credentials.md](2026-08-09-job-account-credentials.md) |
| 2026-08-09 | Mandatory Application Tracking + Resume-Content-in-Interview-Prep | Shipped | [2026-08-09-mandatory-application-tracking.md](2026-08-09-mandatory-application-tracking.md) |
| 2026-08-09 | Parallelize rewriter per-section Claude calls (Tailor/Weave-in speedup) | Shipped | [2026-08-09-parallel-section-rewrite.md](2026-08-09-parallel-section-rewrite.md) |
