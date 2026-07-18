# Worklog — 2026-07-07

**Project:** TexTailor (AI Resume Automator)
**Branch:** `dev`

---

## Summary

Session started as a discussion about which web-fundamentals topics (HTTP/HTTPS,
REST APIs, Cookies & Sessions, JWT, OAuth 2.1) could map onto real TexTailor
features, then narrowed into a concrete spec: a standalone login screen with
mobile+PIN authentication (OTP-verified) plus "Continue with Google" as an
alternate path, built as a portable module inside this repo ("a separate
screen for another project"). Implemented it end-to-end in autonomous mode,
verified the full flow in a real browser via Playwright, then debugged two
issues the user hit running it locally (Windows port conflict, CORS preflight
failure). Nothing has been committed yet — all work is in the working tree.

---

## How to run

```powershell
# Terminal 1 — backend (FastAPI, port 8000)
cd "D:\AI resume automater"
python -m uvicorn src.api:app --reload --reload-dir src --reload-exclude "*.db" --reload-exclude "*.db-*" --port 8000 --log-level info

# Terminal 2 — frontend (Angular, port 4200)
cd "D:\AI resume automater\ui"
ng serve --port 4200
```

Or run both together via `start.ps1` (opens a two-tab Windows Terminal
window) — it calls the same underlying commands via `start-backend.ps1` and
`start-frontend.ps1`, both already updated with the corrected reload flags.

Then open the login screen at `http://localhost:4200/login` (or `/signup` for
a new account) — the resume tool at `http://localhost:4200/` is unaffected.

---

## Work Done

### 1. Discussion — mapping web-auth topics onto TexTailor
Walked through how HTTP/HTTPS, REST APIs, Cookies & Sessions, JWT, and OAuth
2.1 each map onto a real gap in the existing app (no auth at all, a global
in-memory `_tasks` dict shared across every browser tab, `claude_client.py`
shelling out to the personal Claude Code CLI rather than a server-safe API
key). Flagged that real multi-user deployment would need the CLI swapped for
the Anthropic API — noted as a prerequisite, not yet done.

### 2. Design plan — PIN + OTP + Google login screen
User specified the actual flow wanted:
- Signup collects name, mobile number, email (all mandatory)
- Mobile verified via OTP → user then sets a 4-digit PIN
- Returning login: PIN **or** "Continue with Google"

Produced a design doc covering the two flows (signup→OTP→PIN vs. PIN-login /
Google-login), the data model, and six open decisions (SMS gateway, PIN
brute-force protection, forgot-PIN recovery, account linking policy,
Google-only users missing a mobile number, standalone-module vs. integrated).
User approved with "implement it in autonomous mode."

### 3. Implementation — `src/auth/` (backend, FastAPI)
New self-contained module, mounted into `src/api.py`, backed by SQLite
(`src/auth/data/auth.db`, gitignored):

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings — JWT secret, OTP/PIN policy, dev-mode flag |
| `db.py` | Schema (`users`, `otp_requests`, `sessions`) + connection helper |
| `security.py` | bcrypt PIN hashing, JWT issue/decode, OTP hashing |
| `sms.py` | Pluggable `SmsProvider` — `ConsoleSmsProvider` (dev, logs+echoes OTP) / `TwilioSmsProvider` (stub, needs real credentials) |
| `google_oauth.py` | Google Authorization Code + PKCE helpers |
| `schemas.py` | Pydantic request models |
| `router.py` | All `/api/auth/*` endpoints |

Endpoints: `signup`, `otp/send`, `otp/verify`, `pin/set`, `pin/reset`,
`pin/login`, `google/login`, `google/callback`, `complete-mobile`, `me`,
`refresh`, `logout`. PIN lockout after 5 failed attempts (15 min), OTP
expires in 5 min with a 60s resend cooldown and 5 verify attempts, sessions
are JWT access (15 min) + rotated opaque refresh token (30 days) in httpOnly
cookies.

Added `pyjwt`, `bcrypt`, `httpx`, `python-dotenv`, `pydantic[email]` to
`requirements.txt` (relaxed to `>=` pins — exact pins failed to build on the
installed Python 3.14, which is too new for those wheel releases).

### 4. Implementation — `ui/src/app/auth/` (frontend, Angular)
Added routing via `@angular/router` (already a dependency, previously
unused — the app had a single bootstrapped component with no routing). New
root `AppShell` with `<router-outlet>`; `''` still routes to the original
`App` component unchanged, new screens added additively:

`/login`, `/signup`, `/otp`, `/pin-setup`, `/complete-profile`,
`/auth/callback`, `/welcome` — each a standalone component under
`ui/src/app/auth/`, sharing `auth.service.ts` (HTTP calls + transient
signup/OTP flow state) and `auth-shared.scss`.

### 5. Verification — Playwright against a real Chrome instance
No `chromium-cli` or bundled browser available in this sandbox; installed
the `playwright` npm package in the scratchpad and pointed it at the system
Chrome install (`executablePath`) since downloading Playwright's own browser
binary was blocked by network restrictions. Drove the full flow: signup → OTP
(dev-mode code shown on screen) → PIN setup → welcome screen → logout → PIN
login → welcome again → wrong-PIN rejection. Also confirmed the existing
resume tool at `/` still renders with zero regressions.

**Bug caught during verification:** new auth components never called
`ChangeDetectorRef.detectChanges()` — a pattern already established
everywhere in the existing `app.ts` — so `/welcome` rendered blank despite
the `/api/auth/me` call succeeding. Root-caused to an accidental `withFetch()`
addition to `provideHttpClient()` (zone.js doesn't patch `fetch` by default,
so the response resolved outside Angular's zone and never triggered CD).
Removed `withFetch()` and added explicit `detectChanges()` calls to every
auth component to match the codebase's existing convention.

### 6. Documentation
Wrote [`_md/_feature.md`](_md/_feature.md) — architecture, data model,
security notes, how to run, a step-by-step manual test script for every
flow (signup, PIN login, lockout, forgot-PIN, Google), the full API
reference, and known limitations (no real SMS gateway wired up, Google OAuth
needs the user's own credentials, `AUTH_JWT_SECRET` unset means restarts
invalidate sessions).

### 7. Local run debugging (user-reported issues)
- **`WinError 10013` on `uvicorn --reload --port 8000`** — not a venv issue.
  Root cause: a leftover backend process from my own Playwright verification
  step was still bound to port 8000. Found and killed it
  (`Get-NetTCPConnection` → `Stop-Process`).
- **Google button → `501 Not Implemented`** — expected/documented behavior;
  Google OAuth isn't configured until the user adds their own
  `GOOGLE_CLIENT_ID`/`SECRET` to `.env`.
- **Signup → "signup failed"**, backend log showed
  `OPTIONS /api/auth/signup HTTP/1.1" 400 Bad Request` — a failed CORS
  preflight, meaning the browser never sent the actual POST. Widened
  `allow_origins` in `src/api.py` to include both `http://localhost:4200`
  and `http://127.0.0.1:4200`. Verified via direct `curl` preflight
  simulation against Starlette's `CORSMiddleware` source
  (`site-packages/starlette/middleware/cors.py`) that both origins now pass.
  **Still unresolved as of end of session** — user re-tested and hit the
  same 400 after restarting with the origin fix in place; asked them to
  check DevTools Network tab for the actual `Origin` header and the 400
  response body text (which names the specific failed check) to pin it down
  further.
- **Separately caught (not yet confirmed as related):** `uvicorn --reload`
  with no `--reload-dir` watches the entire project tree, including
  `src/auth/data/auth.db` — every signup/OTP/PIN write touches that file and
  would trigger a full server restart, silently invalidating all sessions
  (`AUTH_JWT_SECRET` isn't pinned, so each process start generates a new
  random JWT secret). Fixed `start-backend.ps1` and gave the user the
  corrected command: `--reload-dir src --reload-exclude "*.db" --reload-exclude "*.db-*"`.

---

## Files changed this session (uncommitted)

```
M  .gitignore                       (+ src/auth/data/ ignore rule)
M  requirements.txt                 (+ auth deps)
M  src/api.py                       (mounted auth router, CORS credentials + origins)
M  start-backend.ps1                (reload-dir / reload-exclude fix)
M  ui/src/app/app.config.ts         (provideRouter)
M  ui/src/index.html                (<app-root> → <app-shell>)
M  ui/src/main.ts                   (bootstrap AppShell)
?? .env.example
?? _md/_feature.md
?? src/auth/                        (new backend module)
?? ui/src/app/app-shell.ts
?? ui/src/app/app.routes.ts
?? ui/src/app/auth/                 (new frontend module)
```

`config.json`, `resume/main.pdf`, `resume/main.tex`, `src/agents/rewriter.py`,
`src/claude_client.py`, `ui/src/app/app.ts`, `resume/resume-content.md`,
`2026-06-25.md`, `STARTUP.md` were already modified/untracked before this
session started and weren't touched here.

---

## Signup CORS issue — investigated and resolved (pending user confirmation)

Root cause: the `400` on `OPTIONS /api/auth/signup` was coming from a
backend process still running the pre-fix `allow_origins` (single entry,
`http://localhost:4200` only) from before `127.0.0.1:4200` was added.

Confirmed via a live reproduction against the user's actual running
processes (frontend PID 2608 / `ng serve --open`, backend PID 17524 — both
started 2026-07-08 20:36, i.e. after the CORS fix was already on disk):
drove the real signup form in a headless Chrome instance and captured the
exact request/response — `POST /api/auth/signup` returned `200`, no
preflight rejection, `access-control-allow-origin: http://localhost:4200`
present. Ran the full flow (signup → OTP → PIN setup → welcome → logout →
PIN login → welcome → wrong-PIN rejection) end-to-end against those same
live servers with zero errors.

**Not yet confirmed in the user's own browser** — asked them to retry
`http://localhost:4200/signup` directly. If it still fails there while the
automated reproduction against the same servers succeeds, the next
suspect is something browser-specific (a cached failed preflight from
before the fix, a browser extension, etc.) rather than a server-side bug.

## To-do for tomorrow
- [ ] Confirm in an actual browser (not just the automated repro) that
      signup now completes successfully — if it still fails, get the
      `Origin` header and `400` response body from DevTools Network tab
      for the specific failing request.

### 8. Logged-in indicator on the resume tool page
User asked for the logged-in state to be visible "right within the page"
rather than only on the isolated `/welcome` screen. Clarified scope: added
to the main resume tool page (`/`) itself, not just the auth pages.

- `ui/src/app/app.ts` — injected `AuthService`, added `ngOnInit()` calling
  `me()` (silently, no redirect on 401 — being logged out is a normal state
  on this page, unlike `/welcome`), and a `logout()` method.
- `ui/src/app/app.html` — added a small indicator to the topbar, right of
  "View Template": shows the user's name + a **Log out** button when
  signed in, or a **Log in** link (→ `/login`) when not.
- `ui/src/app/app.scss` — minimal styling to match the existing topbar.

Verified live via Playwright against the running dev server: logged-out
root shows "Log in", signing up and returning to `/` shows the user's name
+ "Log out", and clicking "Log out" from the root page itself reverts back
to "Log in" — all without leaving the resume tool page.

### 9. SMS gateway prerequisites (answered, not yet actioned)
Documented what's needed to move off dev-mode OTP to real Twilio delivery:
a Twilio account + purchased SMS-capable number, `TWILIO_ACCOUNT_SID` /
`TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` in `.env`, `pip install twilio`,
`AUTH_SMS_PROVIDER=twilio` + `AUTH_DEV_MODE=false`. Flagged that Indian
numbers additionally need Twilio DLT (TRAI) registration — a separate,
multi-day approval process — worth weighing against an India-first
alternative like MSG91 before committing to a provider.

## Next Steps
- [ ] Confirm `--reload-dir`/`--reload-exclude` fix stops the reload-on-DB-write loop
- [ ] Pin `AUTH_JWT_SECRET` in `.env` so backend restarts don't invalidate sessions
- [ ] Set up real Google OAuth credentials if Google login is wanted end-to-end
- [ ] Decide on a real SMS provider (Twilio or otherwise) before this leaves dev mode
- [ ] Nothing has been committed yet — review and commit once the CORS issue is resolved
