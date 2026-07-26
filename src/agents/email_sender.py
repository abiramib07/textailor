"""Sends a finalized application email over Gmail SMTP with the resume PDF
attached. No Claude call involved — lives next to `email_generator.py`
because it operates on the same draft shape, not because it's an agent.
"""

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465


def send_email(
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send `body` to `to_addr` with `pdf_bytes` attached as `pdf_filename`.

    Raises RuntimeError if GMAIL_SENDER_ADDRESS/GMAIL_APP_PASSWORD aren't
    configured, or on any SMTP failure (auth, connection, etc.).
    """
    sender = os.environ.get("GMAIL_SENDER_ADDRESS", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not sender or not app_password:
        raise RuntimeError(
            "Gmail sender not configured — set GMAIL_SENDER_ADDRESS and "
            "GMAIL_APP_PASSWORD (see .env.example)"
        )

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = to_addr
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    message.attach(attachment)

    try:
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as server:
            server.login(sender, app_password)
            server.sendmail(sender, [to_addr], message.as_string())
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"Failed to send email: {exc}") from exc
