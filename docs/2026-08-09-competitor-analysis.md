# Competitor Analysis — 2026-08-09

Market research snapshot, not a feature design (see `docs/design-plans/`
for those). Captures where TexTailor stands relative to other AI resume /
job-application tools as of this date, and the feature gaps worth
revisiting later.

## What TexTailor is

An integrated, LaTeX-native job-application pipeline, not just a resume
builder:

- **Generator** — paste a JD → `recruiter` agent analyzes it → `rewriter`
  tailors the actual LaTeX source → compiles to a real PDF → `ats_scorer`
  scores it, with "Weave-in"/"Add to Skills" boost actions for missing
  keywords
- **ATS Score Verifier** — independently re-runs the scoring from scratch
  (not the cached pipeline result) against any resume file or task, as a
  trust check
- **Resume Diff Viewer** — word-level diff between tailored output and the
  original
- **Application Tracker** — tier/status/referral/interview-round/salary
  tracking, upgraded from a simple "Apply Later" list
- **Find Jobs** — live web-search agent with a streaming execution trace
  and a real (non-fabricated, salary-aggregator-verified) salary filter
- **Email Generator** — outreach/application emails, with "Save Context"
  that auto-links to the tracker and seeds the interview-prep checklist
  with JD keywords
- **Job-Site Account Credentials** — an encrypted vault (Fernet) for
  per-company job-site logins, gated behind auth
- **Chat Editor / Resume Import** — conversational resume editing,
  importing an existing resume into the system
- Full auth stack (signup/OTP/PIN/Google OAuth)

## Competitors surveyed

- **Jobscan** — canonical ATS scorer since 2015; tests against named ATS
  systems (Workday, Greenhouse, Taleo, iCIMS) and tunes advice per-system;
  also offers a job tracker.
- **Rezi** — real-time ATS scoring + AI bullet-point rewriting against a
  JD; strong keyword-density control.
- **Teal** — resume tailoring + job tracker combo, strong free tier.
- **Huntr** — tracker-first pipeline management (saved → applied →
  interview stages).
- **Four-Leaf** — rebuilds a fully tailored resume per job application
  (closest analog to our per-job LaTeX regeneration).
- **FastApply / JobCopilot** — combine AI tailoring with auto-apply across
  hundreds/thousands of job boards and company career pages.
- **Kickresume** — general-purpose AI resume builder, broad template
  library.

## Where we stand out

- **LaTeX-native, not template-rendered.** Competitors generate resumes
  from web-form builders or DOCX. TexTailor tailors and recompiles actual
  LaTeX source per job — real typeset output, not an HTML-to-PDF template.
- **Independent verification, not just a single score.** The ATS Score
  Verifier re-runs scoring from scratch rather than trusting a cached
  pipeline number — none of the surveyed competitors advertise a
  self-auditing second opinion like this.
- **Diff transparency.** Seeing exactly what changed between the base and
  tailored resume isn't a feature any surveyed tool calls out.
- **Encrypted job-site credential vault.** Storing per-company job-site
  logins is unusual — most competitors don't touch account credentials at
  all.
- **Everything is linked.** JD → tailored resume → tracker entry →
  interview-prep checklist → email context all thread through shared
  keyword extraction, rather than being separate tools stitched together
  (e.g. Jobscan + Teal + a separate builder).
- **Transparent execution trace on Find Jobs**, with real
  salary-aggregator evidence instead of AI-guessed figures.

## Feature gaps vs. competitors (future TODO)

Nothing here is scheduled — listed for future prioritization, not
in-progress work. Promote any of these to a real
`docs/design-plans/<date>-<slug>.md` entry before implementation.

- [ ] **Auto-apply / bulk-apply.** FastApply and JobCopilot submit
      applications across hundreds/thousands of job boards automatically;
      we only tailor + track, application is still manual.
- [ ] **Named-ATS parser simulation.** Jobscan specifically tests against
      Workday/Greenhouse/Taleo/iCIMS parsing behavior. Our `ats_scorer` is
      keyword/content-based, not simulating specific ATS parsers.
- [ ] **Workday LaTeX-compatibility risk.** LaTeX-exported PDFs are a
      known failure mode for Workday's parser (fonts embedded as images).
      Worth checking whether our compiled PDFs are affected and, if so,
      whether the LaTeX template/compile step can avoid it.
- [ ] **Browser extension / autofill.** Several competitors offer a
      browser extension to autofill applications on company career sites;
      we have nothing browser-side.
- [ ] **Multiple resume templates/formats.** We're LaTeX/single-template;
      competitors typically offer dozens of visual templates plus DOCX
      export.
- [ ] **Mock interview practice.** Our interview-prep is a keyword
      checklist; some competitors offer AI-driven mock interview
      simulations (voice/video Q&A).
- [ ] **Standalone cover-letter artifact.** Our Email Generator covers
      outreach emails but doesn't produce a formal, downloadable cover
      letter alongside the resume the way some competitors do.
