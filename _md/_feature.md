# Login Screen — PIN + OTP + Google OAuth

Standalone auth module built inside TexTailor as a separate, portable screen
(per the original request: "a separate screen for another project"). It does
not touch or gate the existing resume tool — `/` still loads the resume app
exactly as before.

## What it does

- **Sign up** with name, mobile number, email (all mandatory)
- **Mobile verification** via 6-digit OTP
- **4-digit PIN** created right after OTP verification — used for all future logins
- **Login with PIN** (mobile number or email + PIN) as the primary path
- **Login with Google** (OAuth 2.1, Authorization Code + PKCE) as the alternate path
- **Forgot PIN** — re-verify via OTP, then set a new PIN
- **Account linking** — a Google login and a PIN account with the same verified email are treated as one user
- Google-only signups (no mobile number) are routed to a "complete your profile" step to satisfy the mandatory-mobile requirement

## Architecture

```
src/auth/                      Backend module (FastAPI), mounted into src/api.py
  config.py                    Env-driven settings (JWT secret, OTP/PIN policy, dev-mode flag)
  db.py                        SQLite schema (users, otp_requests, sessions) + connection helper
  security.py                  PIN hashing (bcrypt), JWT issue/decode, OTP hashing
  sms.py                       Pluggable SMS provider — ConsoleSmsProvider (dev) / TwilioSmsProvider (real)
  google_oauth.py              Google Authorization Code + PKCE helpers
  schemas.py                   Pydantic request models
  router.py                    All /api/auth/* endpoints

ui/src/app/auth/               Frontend module (Angular), routed additively
  auth.service.ts              HTTP client for /api/auth/*, holds transient signup/otp flow state
  login/                       /login — PIN login + "Continue with Google" + forgot-PIN
  signup/                      /signup — name, mobile, email
  otp/                         /otp — 6-digit code entry, shared by signup / reset / complete-profile
  pin-setup/                   /pin-setup — set or reset the 4-digit PIN
  complete-profile/            /complete-profile — mobile capture for Google-only accounts
  callback/                    /auth/callback — lands here after the Google redirect
  welcome/                     /welcome — post-login profile screen (proves the session works)
```

Routing (`ui/src/app/app.routes.ts`) is additive: `''` still renders the
original `App` (resume tool) component unchanged. The new screens live under
`/login`, `/signup`, `/otp`, `/pin-setup`, `/complete-profile`,
`/auth/callback`, `/welcome`.

## Data model (SQLite — `src/auth/data/auth.db`, gitignored)

| Table | Purpose |
|---|---|
| `users` | name, email, mobile_number, mobile_verified, pin_hash, google_sub, lockout state |
| `otp_requests` | hashed OTP, purpose (`signup`/`reset`/`complete_profile`), expiry, attempts |
| `sessions` | hashed refresh tokens, for rotation/revocation |

## Security notes

- PINs are bcrypt-hashed; **5 failed attempts locks the account for 15 minutes**.
- OTPs are SHA-256-hashed at rest, expire in **5 minutes**, max **5 verify attempts**, **60s** resend cooldown.
- Sessions are a short-lived JWT access token (15 min) + a rotated opaque refresh token (30 days), both httpOnly cookies.
- No real SMS gateway is configured. See "Dev-mode OTP" below.

## Prerequisites

Same as the rest of the project (see [STARTUP.md](../STARTUP.md)), plus the
new Python packages already added to `requirements.txt`:

```powershell
cd "D:\AI resume automater"
python -m pip install -r requirements.txt
```

No new Node packages were needed — `@angular/router` was already a dependency.

## How to run

```powershell
# Terminal 1 — backend
cd "D:\AI resume automater"
python -m uvicorn src.api:app --reload --port 8000

# Terminal 2 — frontend
cd "D:\AI resume automater\ui"
ng serve --port 4200
```

Or use the existing `start.ps1` — it launches both.

The auth DB (`src/auth/data/auth.db`) is created automatically on first
backend startup. No manual migration step.

## How to test

### 1. Signup → OTP → PIN → Welcome
1. Open `http://localhost:4200/signup`
2. Fill in name, mobile number (E.164-ish, e.g. `+919876543210`), email → **Continue**
3. You land on `/otp`. **No real SMS gateway is configured**, so the code is
   shown directly on screen in a blue "Dev mode" banner — copy it.
4. Enter the 6-digit code → **Verify**
5. You land on `/pin-setup`. Enter a 4-digit PIN twice → **Save PIN & continue**
6. You land on `/welcome`, showing your name, email, mobile, and PIN/Google status.

### 2. Log out and log back in with PIN
1. Click **Log out** on `/welcome` → redirects to `/login`
2. Enter the same mobile number (or email) + PIN → **Log in with PIN**
3. Back on `/welcome`.

### 3. Wrong PIN / lockout
Enter the wrong PIN on `/login` — should show "Invalid credentials". After
5 consecutive wrong attempts, the account locks for 15 minutes (HTTP 423).

### 4. Forgot PIN
On `/login`, click **Forgot PIN?** → enter the mobile number → **Send code**
→ same OTP screen (dev-mode code shown) → verify → set a new PIN → lands on
`/welcome`.

### 5. Google login (needs setup first)
Google OAuth is **not configured out of the box** — clicking "Continue with
Google" without credentials returns a clean error, not a crash. To enable it:
1. Create OAuth 2.0 credentials at
   https://console.cloud.google.com/apis/credentials
   (Authorized redirect URI: `http://localhost:8000/api/auth/google/callback`)
2. Copy `.env.example` → `.env` in the project root and fill in
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
3. Restart the backend
4. Click **Continue with Google** on `/login` → Google consent screen →
   redirected to `/auth/callback` → `/welcome` (or `/complete-profile` first,
   if the Google account's email wasn't already linked to a mobile number)

### 6. Confirm the resume tool still works
`http://localhost:4200/` should load the original TexTailor UI — unaffected
by any of the above.

## API reference

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup` | Create pending account, send signup OTP |
| POST | `/api/auth/otp/send` | (Re)send OTP for `signup` \| `reset` \| `complete_profile` |
| POST | `/api/auth/otp/verify` | Verify OTP → returns short-lived `otp_verified_token` |
| POST | `/api/auth/pin/set` | First-time PIN creation (needs `otp_verified_token`, purpose=signup) |
| POST | `/api/auth/pin/reset` | New PIN after forgot-PIN (needs `otp_verified_token`, purpose=reset) |
| POST | `/api/auth/pin/login` | Login with mobile/email + PIN |
| GET | `/api/auth/google/login` | Redirect to Google consent screen |
| GET | `/api/auth/google/callback` | Google redirects here; creates/links account, issues session |
| POST | `/api/auth/complete-mobile` | Attach + verify mobile number for a Google-only account |
| GET | `/api/auth/me` | Current user profile (requires session) |
| POST | `/api/auth/refresh` | Rotate access/refresh tokens |
| POST | `/api/auth/logout` | Revoke session |

## Known limitations / things deferred

- **No real SMS gateway wired up** — `AUTH_SMS_PROVIDER=console` (default)
  just logs the OTP and echoes it in the API response when
  `AUTH_DEV_MODE=true`. A `TwilioSmsProvider` stub exists in `src/auth/sms.py`
  — set `AUTH_SMS_PROVIDER=twilio` + Twilio credentials in `.env` and set
  `AUTH_DEV_MODE=false` to go live.
- **Google OAuth requires your own credentials** — not runnable until
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set.
- **`AUTH_JWT_SECRET` is random per process if unset** — sessions won't
  survive a backend restart until it's pinned in `.env`.
- This screen is **not wired into the rest of TexTailor** (no route guards on
  the resume tool) — by design, since it was requested as a standalone screen
  for a separate project.
