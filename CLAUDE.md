# TexTailor — Project Rules

## Coding standards are non-negotiable

Every code change in this repo — new feature, bug fix, or refactor — must
meet the standards below before it's considered done. This applies
regardless of how small the change is.

### Backend (`src/`, Python)

- **Tooling is configured in `pyproject.toml`** (ruff + mypy). Before
  considering any Python change done, run:
  ```powershell
  python -m ruff check src
  python -m ruff format src
  python -m mypy src
  ```
  All three must pass clean. Don't add `# type: ignore` or ruff
  `noqa`/ignore rules to silence a finding unless the finding is a genuine
  false positive — fix the underlying issue first.
- **Every module, class, function, and method needs a docstring** — one
  concise line unless the behavior genuinely needs more (args/returns for
  non-obvious contracts). No exceptions for "obviously named" functions —
  `ruff check --select D` enforces this.
- **Every function signature needs type hints**, including return types.
  Avoid `Any` unless the value genuinely is dynamic (e.g. parsed JSON).
- **snake_case** for functions/variables/files, **PascalCase** for classes,
  **UPPER_SNAKE_CASE** for module-level constants. Already consistent
  throughout — keep it that way.
- New agents (Claude-backed, single-purpose, prompt-in/JSON-out) go in
  `src/agents/`. New auth-related code goes in `src/auth/`. Don't scatter
  agent logic into `api.py` — routes call into agents, they don't contain
  prompt logic themselves (see any existing route in `api.py` for the
  pattern: thin route, real work delegated to `agents/*.py`).

### Frontend (`ui/src`, Angular/TypeScript)

- **TypeScript `strict` mode and Angular `strictTemplates` are on** in
  `tsconfig.json` — don't weaken either to make an error go away; fix the
  type issue.
- **ESLint is wired to `ng lint`** (`@angular-eslint`). Before considering
  any frontend change done, run:
  ```powershell
  cd ui
  npx ng lint
  npx ng build
  ```
  Both must pass clean (warnings on the initial bundle/style budgets are
  pre-existing and acceptable; new errors are not).
- **Modern Angular conventions, not legacy ones**:
  - Use `@if` / `@for` / `@switch` (built-in control flow), never
    `*ngIf` / `*ngFor` / `*ngSwitch`.
  - Use `inject()` for dependency injection, not constructor-parameter
    injection.
  - Components omit the `.component` suffix in filenames (`login.ts`, not
    `login.component.ts`); services and guards keep their type suffix
    (`auth.service.ts`, `auth.guard.ts`). This split is deliberate —
    match it for new files.
- **Accessibility is not optional.** Every `<label>` must be associated
  with its control via `for`/`id` (never nest `<label>` inside `<label>`).
  Every element with a `(click)` handler must be a real interactive
  element (`<button>`, `<a href>`) or have an equivalent keyboard handler
  — `ng lint` will catch violations via `@angular-eslint/template/*`
  accessibility rules.

## File / project structure

Don't restructure existing files (move, rename, or split) without being
asked — `src/api.py` in particular is intentionally kept as one file for
now (a domain-router split was discussed and explicitly deferred). Adding
new, well-organized files following the existing layout is always fine;
reorganizing existing ones is a separate, larger decision each time.

Current top-level layout:

```
src/
  api.py              FastAPI app + all HTTP routes (routes are thin, delegate to agents/)
  main.py             CLI entry point (file-watcher variant of the same pipeline)
  claude_client.py     shared subprocess wrapper around the Claude Code CLI
  latex_parser.py, latex_patcher.py, compiler.py, md_converter.py, history.py
  agents/             one file per Claude-backed agent (recruiter, rewriter,
                       ats_scorer, verifier, chat_editor, editor, email_generator)
  auth/                standalone login module (router, db, security, sms, config, schemas)

ui/src/app/
  app.ts / app.html / app.scss     resume-tool root component (Generator / Resume Editor / Email Generator tabs)
  resume.service.ts                typed HTTP client for the core pipeline API
  auth/                            login module (login, signup, otp, pin-setup, welcome, etc.)
  email-generator/                 email-generator tab, self-contained (own service + component)
```

New features get their own file/folder following this pattern — a new
agent is a new file in `agents/`, a new frontend feature is a new folder
under `ui/src/app/` with its own component + service, not code bolted onto
an existing unrelated file.

## Verifying before calling something done

For backend changes: run the lint/type/format commands above, then
actually start the server and hit the affected endpoint (curl or the
`run` skill) — a clean lint pass doesn't mean the code works.

For frontend changes: run lint/build above, then drive the actual UI in a
browser for anything touching a template — see the `verify` skill.

## Git hygiene

Before every `git add` / commit / push, check `git status` for anything
that looks like a scratch note rather than a real project file — dated
worklog dumps, session-continuation notes, one-off TODO lists, throwaway
prototype files. These are useful locally but don't belong in the repo.
`_md/`, `session-history/`, and known one-off names (`TODO.md`,
`CONTINUE_HERE.md`, `worklog-update.md`, `issue-log.md`,
`email_generator_tab.html`) are already gitignored — if a new file in
that spirit shows up, add it to `.gitignore` rather than committing it.
Real docs (`ARCHITECTURE.md`, `AGENTS.md`, `STARTUP.md`, `UI_SETUP.md`,
`design_plan.md`, etc.) are not affected by this — only throwaway notes.

**Commit messages are one short line** — what changed, not a narrative.
No multi-paragraph bodies, no restating the diff. E.g. `Fix ATS score
rounding in ats_scorer.py`, not a story about why or how.
