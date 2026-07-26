"""
Email Generator Agent — turns a raw pasted job post (e.g. a LinkedIn post,
not the structured JD box) into a ready-to-send application email.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_GENERATE_PROMPT = """You are helping a candidate write a professional application email for a job they found online.

Read the job post below and the candidate's resume, then write a concise, ATS-friendly email suitable for
referrals, recruiters, or direct applications. If a recruiter/hiring manager name appears in the job post,
address them by name; otherwise use "Hiring Manager". Mention 3-4 concrete matched skills/tools from the resume,
not a generic summary.

The body is plain text, not markdown — it will be sent as-is in an email client. Do NOT use **bold**,
bullet characters like "-" or "*", or any other markdown syntax. Write plain sentences and paragraphs only.

Extra instruction from the candidate: {instruction}
{learned_patterns}
Output ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "role_title": "job title extracted from the post",
  "company_name": "hiring company's name extracted from the post, or empty string if the post never names it",
  "to": "hiring.manager@company.com or a name if no email is given",
  "subject": "Application for <role> — <candidate name from resume>",
  "body": "The full email body as plain text with \\n\\n between paragraphs. End with a sign-off using the candidate's ACTUAL name, phone, email, and LinkedIn/GitHub links exactly as they appear in the resume's Contact Info section below — never a placeholder like '[Your Name]' or '[Your Phone]'."
}}

JOB POST:
{job_post}

RESUME:
{resume}
"""

_REVISE_PROMPT = """You previously drafted this application email. The candidate wants a change.

CURRENT EMAIL:
To: {to}
Subject: {subject}
Body:
{body}

CANDIDATE'S REQUEST: {instruction}

RESUME (for reference, don't invent anything not here):
{resume}

The body is plain text, not markdown — no **bold**, no "-"/"*" bullets. Plain sentences and paragraphs only.

Output ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "to": "...",
  "subject": "...",
  "body": "...",
  "done_summary": "one sentence describing what changed"
}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _format_learned_patterns(patterns: list[str] | None) -> str:
    """Render past revision instructions as a prompt block, or "" if none yet."""
    if not patterns:
        return ""
    bullet_list = "\n".join(f"- {p}" for p in patterns)
    return (
        "\nThe candidate has taught you these preferences from past revisions — "
        f"apply them by default unless they conflict with the instruction above:\n{bullet_list}\n"
    )


def generate_email(
    job_post_text: str,
    resume_plain_text: str,
    instruction: str,
    learned_patterns: list[str] | None = None,
) -> dict:
    """Draft an application email (to/subject/body/role_title) from a raw
    job post and the candidate's resume, applying any previously learned
    revision preferences automatically."""
    prompt = _GENERATE_PROMPT.format(
        instruction=instruction.strip()
        or "Write a professional email to apply for this role, referencing my resume.",
        learned_patterns=_format_learned_patterns(learned_patterns),
        job_post=job_post_text.strip(),
        resume=resume_plain_text.strip(),
    )
    raw = _strip_fences(ask_claude(prompt))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Email generator: no JSON in Claude response:\n{raw[:400]}")
    return json.loads(match.group())


def revise_email(current: dict, instruction: str, resume_plain_text: str) -> dict:
    """Apply a chat-style revision instruction to an existing email draft."""
    prompt = _REVISE_PROMPT.format(
        to=current.get("to", ""),
        subject=current.get("subject", ""),
        body=current.get("body", ""),
        instruction=instruction.strip(),
        resume=resume_plain_text.strip(),
    )
    raw = _strip_fences(ask_claude(prompt))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Email generator: no JSON in Claude response:\n{raw[:400]}")
    return json.loads(match.group())
