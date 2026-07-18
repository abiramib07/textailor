"""Pluggable SMS delivery for OTPs: a dev-only console provider and a Twilio
provider, selected at runtime via `AUTH_SMS_PROVIDER`.
"""

import logging
from abc import ABC, abstractmethod

from . import config

log = logging.getLogger("textailor.auth.sms")


class SmsProvider(ABC):
    """Interface every SMS backend implements."""

    @abstractmethod
    def send_otp(self, mobile_number: str, otp: str) -> None:
        """Deliver an OTP code to a mobile number."""
        ...


class ConsoleSmsProvider(SmsProvider):
    """Dev-only provider — logs the OTP instead of sending a real SMS.

    No SMS gateway account exists for this project yet. Swap AUTH_SMS_PROVIDER
    to a real provider (e.g. "twilio") once credentials are available; every
    call site already goes through send_otp() so nothing else changes.
    """

    def send_otp(self, mobile_number: str, otp: str) -> None:
        """Log the OTP instead of sending it — dev mode only."""
        log.info(
            "[DEV SMS] OTP for %s is %s (expires in %ss)",
            mobile_number,
            otp,
            config.OTP_TTL_SECONDS,
        )


class TwilioSmsProvider(SmsProvider):
    """Real SMS delivery via Twilio. Requires the `twilio` package and
    TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER to be set.
    """

    def __init__(self) -> None:
        if not (
            config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM_NUMBER
        ):
            raise RuntimeError(
                "AUTH_SMS_PROVIDER=twilio but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / "
                "TWILIO_FROM_NUMBER are not all set."
            )
        from twilio.rest import Client  # local import — optional dependency

        self._client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

    def send_otp(self, mobile_number: str, otp: str) -> None:
        """Send the OTP as a real SMS via the Twilio API."""
        self._client.messages.create(
            body=f"Your TexTailor verification code is {otp}. It expires in 5 minutes.",
            from_=config.TWILIO_FROM_NUMBER,
            to=mobile_number,
        )


def get_sms_provider() -> SmsProvider:
    """Return the configured SMS provider (`AUTH_SMS_PROVIDER`; console by default)."""
    if config.SMS_PROVIDER == "twilio":
        return TwilioSmsProvider()
    return ConsoleSmsProvider()
