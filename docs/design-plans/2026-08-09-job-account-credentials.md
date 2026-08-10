# Job-Site Account Credentials — store email/password per company account

**Status:** Shipped
**Date:** 2026-08-09

## Context

Applying to companies routinely means creating a new account on their
career portal (Workday, Greenhouse, Lever, a company's own ATS, etc.) —
each with its own email/username + password. Today there's nowhere in the
app to keep track of these, so the user re-triggers "forgot password" or
digs through a personal notes app whenever they need to log back in to
check application status. This mirrors `personal_info` (existing
per-resume-identity key/value clipboard) and `apply_later` (existing
per-resume-identity tracker) in shape — a small CRUD list scoped to the
active resume identity — except the core content is a **secret** that must
be stored so it can be decrypted and shown back to the user later, not
just hashed like the app's own login PIN.

## Decisions (proposed — pending user review)

1. **New standalone module, not bolted onto `career`:** `src/credentials/`
   (own `db.py` / `schemas.py` / `router.py`, own SQLite file
   `src/credentials/data/credentials.db`), mounted into `api.py` exactly
   like `auth`/`career`/`resumes` are today (`init_db()` call in
   `_startup()`, `app.include_router(credentials_router)`). Reasoning:
   `career.db` currently holds only plaintext, low-sensitivity data (notes,
   URLs, checklist items); passwords are meaningfully more sensitive and
   deserve their own encryption-key lifecycle and their own gitignored data
   directory, rather than commingling encrypted secrets into a DB file
   whose other tables are plain SQL columns. This follows the existing
   "new feature → new file/folder" layout rule in `CLAUDE.md` — same
   pattern as `career`/`resumes`/`auth` each being their own module.
2. **Reversible encryption, not hashing.** The whole point is to view the
   password again later, so bcrypt (used for the login PIN) doesn't apply.
   Adds `cryptography` (Fernet — AES128-CBC + HMAC, authenticated
   symmetric encryption) as a new dependency in `requirements.txt` and
   `pyproject.toml`. New `src/credentials/crypto.py`:
   `encrypt(plaintext) -> str` / `decrypt(token) -> str`, key sourced from
   `CREDENTIALS_ENC_KEY` env var if set, else **generated once and
   persisted** to a gitignored `src/credentials/data/.enc_key` file (NOT
   regenerated per-process like `auth.config.JWT_SECRET`'s dev fallback —
   losing that key permanently bricks every stored password, unlike a JWT
   secret rotation which just logs sessions out). This distinction will be
   called out in a code comment and in `STARTUP.md`/`.env.example` if one
   exists, recommending `CREDENTIALS_ENC_KEY` be set explicitly and backed
   up outside the repo for anything beyond local dev.
3. **List view never returns plaintext passwords.** `GET
   /api/credentials` returns `has_password: bool` per entry, not the
   decrypted value. A separate `GET /api/credentials/{id}/reveal` decrypts
   and returns the password only when the user explicitly clicks "Show" —
   mirrors the existing copy-to-clipboard pattern in
   `personal-info.ts::copy()`, minimizes plaintext-secret exposure in the
   list payload/devtools network tab/console logs by default.
4. **Fields:** `company_name`, `site_url`, `login_email`, `username`
   (optional — some ATS portals require a separate username from email,
   e.g. Workday), `password` (encrypted at rest), `notes` (optional free
   text, e.g. security question answers) — scoped by `resume_id` exactly
   like `apply_later`/`personal_info`, since credentials are naturally
   per job-hunt identity.
5. **Gate every `/api/credentials/*` route behind login**, via
   `Depends(get_current_user)` (`auth/router.py:102-123`, already used by
   `/api/auth/me`) — unlike `career`/`resumes`, which are unguarded today.
   This costs nothing UX-wise: `app.routes.ts` already gates the entire
   app root behind `authGuard`, so a session cookie always exists by the
   time any tab renders. Storage stays keyed by `resume_id` (matches how
   the user already thinks about per-identity job hunts), but the route
   layer additionally requires a valid session — defense-in-depth
   specifically because this is the one feature in the app that stores
   real secrets rather than notes/URLs, unlike the rest of `career`.
   `job-credentials.service.ts` passes `withCredentials: true` on every
   call (same as `auth.service.ts`) so the cookie is sent.
6. **UI placement:** a new "Account Credentials" entry in the existing
   "Career Tools" dropdown (`app.ts::careerTabs`), alongside Personal Info
   / Application Tracker / LinkedIn Archive / Interview Prep / Topic
   Mapping — new component folder `ui/src/app/career/job-credentials/`
   with its own `job-credentials.ts`/`.html`/`.scss` and its own
   `job-credentials.service.ts` (pointing at `/api/credentials`, separate
   from `career.service.ts` since the backend module is separate too).
   List rendered as a table (company, URL, email/username, masked
   password with a "Show"/"Copy" button per row, notes), matching the
   `apply-later` table's visual style.

## Planned backend (`src/credentials/`)

- `db.py`: SQLite schema —
  ```sql
  CREATE TABLE credentials (
      id             TEXT PRIMARY KEY,
      resume_id      TEXT NOT NULL,
      company_name   TEXT NOT NULL,
      site_url       TEXT,
      login_email    TEXT NOT NULL,
      username       TEXT,
      password_enc   TEXT NOT NULL,
      notes          TEXT,
      created_at     REAL NOT NULL,
      updated_at     REAL NOT NULL
  );
  CREATE INDEX idx_credentials_resume ON credentials(resume_id);
  ```
  Same `get_conn()`/`tx()` thread-local pattern as `auth.db`/`career.db`.
- `crypto.py`: `encrypt`/`decrypt` wrapping `cryptography.fernet.Fernet`,
  `_load_or_create_key()` handling the env-var-or-persisted-file logic
  from decision 2.
- `schemas.py`: `CredentialCreate` (resume_id, company_name, site_url,
  login_email, username, password, notes), `CredentialUpdate` (all
  fields optional, only provided ones change — password re-encrypted only
  if provided, so editing notes doesn't require re-entering the password).
- `router.py` (`/api/credentials`, mounted in `api.py`,
  `APIRouter(prefix="/api/credentials", dependencies=[Depends(get_current_user)])`
  so every route below requires a valid session — see decision 5):
  - `POST /api/credentials` — create, encrypts password before insert.
  - `GET /api/credentials?resume_id=` — list for a resume identity,
    `password_enc` never serialized; response includes `has_password: true`.
  - `GET /api/credentials/{id}/reveal` — decrypt and return `{password:
    str}` only; 404 if not found.
  - `PATCH /api/credentials/{id}` — partial update; re-encrypts only when
    `password` is provided in the body.
  - `DELETE /api/credentials/{id}` — remove.
- `_startup()` in `api.py` gains `init_credentials_db()` alongside the
  other module inits; `app.include_router(credentials_router)` added next
  to the other three.
- `requirements.txt` / `pyproject.toml`: add `cryptography>=42`.
- `.gitignore`: add `src/credentials/data/` (DB file + the persisted key
  file both live there — same gitignore shape as `src/auth/data/` and
  `src/career/data/`).

## Planned frontend (`ui/src/app/career/job-credentials/`)

- `job-credentials.service.ts`: `list()`, `create(...)`, `update(id,
  fields)`, `delete(id)`, `reveal(id): Observable<{password: string}>` —
  same `HttpClient` + `withCredentials: true` pattern as `career.service.ts`.
- `job-credentials.ts`/`.html`/`.scss`: table of saved accounts (company,
  URL, email/username, masked password + "Show" (calls `reveal()` on
  click, auto-re-masks after ~10s like a real password manager) + "Copy"
  buttons, notes), an add-entry form, inline edit, delete with confirm.
  Follows `apply-later.ts`'s table-row-CRUD structure, not
  `personal-info.ts`'s flat key/value form (this data has more structured
  fields per row).
- `app.ts`: add `'job-credentials'` to the `Tab` union and to
  `careerTabs`; `app.html` gets a new `@if (activeTab === 'job-credentials')`
  block rendering `<app-job-credentials>` (matching the existing chained
  `@if` tab-switch pattern — this app doesn't use `@switch` for tabs), and
  the new component added to `App`'s `imports`. `@if`-destroyed like the
  other career sub-tabs (no in-flight async state worth preserving across
  a tab switch here, unlike `email-generator`/`import-resume`, which stay
  permanently mounted for that reason).

## Verification plan

- `ruff check src`, `ruff format src`, `mypy src` clean.
- `ng lint`, `ng build` clean.
- New `tests/test_credentials.py`:
  - `crypto.py`: `decrypt(encrypt(x)) == x` round-trip; a tampered
    ciphertext raises rather than silently returning garbage (Fernet is
    authenticated, so this is free correctness to verify, not extra code).
  - `db.py`/`router.py` via FastAPI `TestClient` (same pattern as
    `tests/test_api_verify_features.py`, no Claude call involved at all
    here so nothing to monkeypatch): create → list shows `has_password:
    true` and no `password`/`password_enc` key anywhere in the list
    response body → reveal returns the correct plaintext → update notes
    only leaves password unchanged (reveal still returns the original) →
    update password re-encrypts (reveal returns the new value) → delete
    removes it (subsequent reveal 404s) → list is scoped to `resume_id`
    (a second resume identity's entries don't leak into the first's list)
    → every route 401s with no session cookie (asserts decision 5's
    `Depends(get_current_user)` gate actually took effect, using the same
    `TestClient` without the login flow first).
- Live smoke test: start the server, create a real entry through the UI,
  restart the server (simulating a real dev-loop reload), confirm reveal
  still decrypts correctly — this specifically exercises the
  persisted-key-file path from decision 2, since an in-memory-only key
  would silently break exactly on this step.

## Explicitly not doing (this round)

- No password-strength meter or generator — this is a storage/retrieval
  tool for accounts the user already created, not a signup helper.
- No per-field audit history (e.g. "password changed 3 times") — a single
  current value per entry, like the rest of the career-tools tables.
- No sharing/export — single local user, no multi-user access model exists
  anywhere else in this app either.
- Not retrofitting login-gating onto `career`/`resumes` — decision 5 only
  adds `Depends(get_current_user)` to the new `/api/credentials` routes;
  bringing the rest of the app's HTTP surface up to the same bar is a
  separate, larger decision out of scope here.

## Shipped

- `src/credentials/` (`crypto.py`, `db.py`, `schemas.py`, `router.py`),
  matching the plan exactly: Fernet encrypt/decrypt with a
  `CREDENTIALS_ENC_KEY`-env-var-or-persisted-`.enc_key`-file key,
  thread-local SQLite connection (`career`/`auth`-style), `/api/credentials`
  gated by `Depends(get_current_user)`. Mounted in `api.py`
  (`init_credentials_db()` in `_startup()`, router included alongside
  `auth`/`career`/`resumes`). `cryptography>=42` added to
  `requirements.txt` and `pyproject.toml`; `src/credentials/data/`
  gitignored.
- `ui/src/app/career/job-credentials/` — `job-credentials.ts`/`.html`/
  `.scss` (table CRUD matching `apply-later`'s visual style) +
  `job-credentials.service.ts` (`withCredentials: true`, matching
  `auth.service.ts`). New "Account Credentials" entry in the Career Tools
  dropdown; `@if`-destroyed tab in `app.html`, matching the other career
  sub-tabs.
- Verified: `ruff check`/`ruff format`/`mypy` clean; `ng lint`/`ng build`
  clean (one new type-accuracy warning surfaced and fixed along the way —
  `revealedPasswords` needed `Record<string, string | undefined>`, not
  `Record<string, string>`, since TS doesn't otherwise know a lookup can
  miss).
- **Tests written before the implementation** (`tests/test_credentials.py`,
  13 cases) — confirmed all 13 failed with import errors before
  `src/credentials/` existed, then all 13 passed once it was built,
  catching two real bugs along the way:
  1. `_load_or_create_key(key_path: Path = KEY_PATH)`'s default parameter
     was bound at function-definition time, so monkeypatching the module's
     `KEY_PATH` for a test had no effect — `_get_fernet()` now passes
     `KEY_PATH` explicitly at call time instead of relying on the default.
  2. The test fixture itself was wrong for `auth.db`: `DB_PATH` lives on
     `auth.config` but the thread-local connection cache lives on
     `auth.db` — a different module. Fixed the fixture, not the app code.
  Full suite (`tests/`, 43 cases) passes with no regressions.
- Live smoke test against the real running server (not just `TestClient`):
  signed up a throwaway account through the actual `/api/auth/*` flow,
  confirmed every `/api/credentials/*` route 401s with no session cookie,
  created/listed/revealed/updated/deleted a real credential over HTTP,
  confirmed the list response never contains `password`/`password_enc`,
  then **fully killed the backend process and started a brand-new one**
  (not `--reload`, a genuine cold start) and confirmed the stored password
  still decrypted correctly — the specific failure mode decision 2 was
  designed to prevent. Frontend: `ng lint`/`ng build` are clean, but a
  full browser click-through could not be completed in this environment
  (no browser-automation tool available, and port 4200 was already held by
  an existing process) — this is a real gap, not a claimed pass; a manual
  browser check of the new tab is still worth doing before relying on it
  day-to-day.
