# SMS Gateway Setup (Production Prerequisite)

TexTailor's login module (`src/auth/`) sends OTPs through a pluggable
`SmsProvider` interface (`src/auth/sms.py`). By default it runs in
**dev mode**: OTPs are logged to the console and echoed back in the API
response (`dev_otp` field) instead of being texted anywhere. This is fine
for local development but must not ship to anyone but you.

## Before enabling real SMS delivery

1. **A Twilio account** — sign up at twilio.com. A free trial works for
   testing, but trial accounts can only send to phone numbers you've
   manually verified in the Twilio console first.
2. **A Twilio phone number** capable of sending SMS — bought inside the
   console; costs a small monthly fee outside the trial.
3. **Three credentials** from the Twilio console.
4. **The `twilio` Python package** — commented out in `requirements.txt`
   until needed:
   ```powershell
   python -m pip install twilio
   ```
   then uncomment the `twilio` line in `requirements.txt`.

## Configuration

Add to `.env` (never commit this file — it's gitignored):

```
AUTH_SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
AUTH_DEV_MODE=false
```

`AUTH_DEV_MODE=false` is what actually stops OTPs from being echoed back in
API responses — leaving it `true` with a real provider configured would
both send a real SMS *and* leak the code in the HTTP response, which
defeats the purpose of 2FA.

Restart the backend after changing `.env`.

## India-specific note (DLT registration)

If you're sending to Indian phone numbers, Twilio additionally requires
**DLT registration** — TRAI's mandatory sender-ID and message-template
registration for commercial SMS. This is a separate, multi-day approval
process independent of creating the Twilio account itself, and is easy to
underestimate when planning a launch date.

**Alternative worth weighing:** MSG91 handles DLT registration as part of
its own onboarding flow, which can be simpler for an India-first product
than doing DLT + Twilio separately. Neither is wired up in code yet — only
`ConsoleSmsProvider` (dev) and a `TwilioSmsProvider` stub exist in
`src/auth/sms.py`. Adding MSG91 would mean writing a new `SmsProvider`
subclass there; the rest of the auth module (OTP generation, hashing,
expiry, rate limiting) doesn't need to change.

## Where this plugs in

`src/auth/sms.py`:
```python
def get_sms_provider() -> SmsProvider:
    if config.SMS_PROVIDER == "twilio":
        return TwilioSmsProvider()
    return ConsoleSmsProvider()
```

Every OTP send in the auth module goes through `get_sms_provider().send_otp(...)`
— switching providers is a one-line config change (`AUTH_SMS_PROVIDER`),
not a code change, as long as the new provider class exists.
