"""Windows toast notifications on task completion, via `plyer`.

Fire-and-forget: a notification failure (e.g. no notification backend
available in a headless/CI environment) must never break the pipeline that
triggered it, so every call is wrapped and logged rather than raised.
"""

import logging

from plyer import notification

log = logging.getLogger("textailor.notifier")

APP_NAME = "TexTailor"


def notify(title: str, message: str) -> None:
    """Show a Windows toast notification. Never raises."""
    try:
        notification.notify(title=title, message=message, app_name=APP_NAME, timeout=8)
    except Exception:
        log.exception("Failed to show notification: %s — %s", title, message)


def notify_resume_done(job_title: str, score: float, verdict: str) -> None:
    """Notify that a resume-tailoring pipeline run finished successfully."""
    notify(
        "Resume ready",
        f"{job_title} — {score}% ATS match ({verdict})",
    )


def notify_resume_failed(job_title: str, error: str) -> None:
    """Notify that a resume-tailoring pipeline run failed."""
    notify("Resume generation failed", f"{job_title}: {error[:120]}")


def notify_email_done(role_title: str) -> None:
    """Notify that an application email draft is ready."""
    notify("Email draft ready", f"Application email for {role_title} is ready to review")
