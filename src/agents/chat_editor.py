"""
Chat Editor Agent — two-phase: plan → confirm → execute.

Phase 1 (plan):  Claude reads the user message, explains in plain English what it will do.
                 No changes are made yet.
Phase 2 (execute): User confirmed — Claude generates LaTeX patches, backs up the file,
                 applies patches, and compiles. Auto-reverts if compilation fails.
"""

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude
from compiler import compile_tex

_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_RESUME = _ROOT / "resume" / "main.tex"

# How many prior turns to replay back to Claude so it can resolve references
# like "the above", "that", or a short reply to its own previous question.
_MAX_HISTORY_TURNS = 12


def _backups_dir(resume_path: Path) -> Path:
    """Backups live next to the resume they belong to, keeping each resume
    identity's undo history separate."""
    return resume_path.parent / "backups"


def _format_history(history: list[dict] | None) -> str:
    """Render prior plan-phase turns as a transcript block for the prompt,
    or "" if there's no history yet."""
    if not history:
        return ""
    lines = [
        f"{'User' if turn['role'] == 'user' else 'You (assistant)'}: {turn['text']}"
        for turn in history[-_MAX_HISTORY_TURNS:]
    ]
    return "CONVERSATION SO FAR (earlier turns in this session):\n" + "\n".join(lines) + "\n\n"


_PLAN_PROMPT = """You are a resume editor assistant. The user wants to modify their LaTeX resume.

{history_block}Analyse the LATEST USER MESSAGE below — using the conversation history above (if any) to \
resolve references like "the above", "that", or a short reply to your own previous question — and return \
ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "intent_type": "layout-change | content-remove | content-shorten | content-rewrite | add-content | unknown",
  "summary": "One clear sentence describing exactly what you will do — must be self-contained, combining everything agreed on so far, not just the latest message",
  "changes_preview": [
    "Human-readable description of specific change 1",
    "Human-readable description of specific change 2"
  ],
  "questions": [],
  "confidence": "high | medium | low"
}}

If the request is still ambiguous after considering the history (confidence low or medium), put clarifying
questions in "questions" and leave changes_preview empty. Do NOT generate any LaTeX. Just explain the plan
in plain English.

LATEST USER MESSAGE:
{message}

CURRENT RESUME (resume/main.tex):
{resume_tex}
"""

_EXECUTE_PROMPT = """You are a LaTeX resume editor. The user has approved the plan below. Now execute it.

Return ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "patches": [
    {{"old": "exact verbatim string from resume.tex", "new": "replacement string"}},
    ...
  ],
  "done_summary": "One sentence confirming what was done"
}}

CRITICAL RULES:
- Your entire response must be valid JSON. Every backslash that appears in LaTeX content inside "old" or
  "new" (\\href, \\textbf, \\,, \\&, etc.) MUST be written as a doubled backslash in your JSON output —
  e.g. the LaTeX \\href{{url}}{{text}} must appear in your JSON string as \\\\href{{url}}{{text}} (curly
  braces stay single — only backslashes double). A single un-escaped backslash makes the whole response
  unparsable.
- "old" must be a character-perfect verbatim substring copied directly from resume.tex — no alterations
- "new" must use only existing macros: \\projectheading{{}}, \\bulletpoints{{}}, \\bulletitem{{}}, \\techline{{}}, \\jobheading{{}}, \\textbf{{}}, \\href{{}}{{}}
- LaTeX escaping in "new": & → \\&  |  arrow → $\\rightarrow$  |  % → \\%  |  # → \\#
- For font size change: find the exact \\fontsize{{X}}{{Y}} lines in the preamble and replace the numbers only
- For margin change: find exact margin=X.XXin in \\usepackage[...]{{geometry}} and replace value only
- For spacing: find exact \\vspace{{Xpt}} or \\titlespacing values and replace
- For removing a project: "old" must be the entire block from \\projectheading to the closing \\techline line + trailing blank lines
- Make the MINIMUM change needed — only touch what the plan says to change

APPROVED PLAN: {plan_summary}
ORIGINAL USER REQUEST: {message}

CURRENT RESUME (resume/main.tex):
{resume_tex}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


_VALID_JSON_ESCAPES = set('"\\/bfnrtu')


def _repair_json_backslashes(raw: str) -> str:
    """Fix the most common way Claude's JSON responses break: LaTeX content
    (\\href, \\textbf, \\,, ...) embedded in a JSON string with its
    backslashes left single instead of doubled, which isn't valid JSON.
    Escapes any backslash not already part of a legal JSON escape sequence.
    """
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\\" and i + 1 < n and raw[i + 1] in _VALID_JSON_ESCAPES:
            out.append(raw[i : i + 2])
            i += 2
            continue
        if ch == "\\":
            out.append("\\\\")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_json_response(raw: str) -> dict:
    """Parse a JSON object from Claude, retrying with backslash repair once
    before giving up — see `_repair_json_backslashes`."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_repair_json_backslashes(raw))


def _next_backup_path(resume_path: Path) -> Path:
    backups = _backups_dir(resume_path)
    backups.mkdir(parents=True, exist_ok=True)
    existing = sorted(backups.glob("v*.tex"))
    n = len(existing) + 1
    return backups / f"v{n}.tex"


def plan(
    message: str, resume_path: Path = _DEFAULT_RESUME, history: list[dict] | None = None
) -> dict:
    """
    Phase 1: analyse the user's request and return a plain-English plan.
    No changes are made to the resume.

    `history` is the running plan-phase transcript for this resume's current
    editing session (list of {"role": "user"|"assistant", "text": str}), so
    follow-up messages ("add the above", answering a clarifying question) can
    be resolved instead of analysed in isolation.

    Returns dict with keys: intent_type, summary, changes_preview, questions, confidence, plan_id (added by caller)
    """
    resume_tex = resume_path.read_text(encoding="utf-8")
    prompt = _PLAN_PROMPT.format(
        history_block=_format_history(history), message=message, resume_tex=resume_tex
    )
    raw = _strip_fences(ask_claude(prompt))
    try:
        return _parse_json_response(raw)
    except json.JSONDecodeError:
        return {
            "intent_type": "unknown",
            "summary": "Could not analyse the request — please rephrase it.",
            "changes_preview": [],
            "questions": [],
            "confidence": "low",
        }


def execute(message: str, plan_summary: str, resume_path: Path = _DEFAULT_RESUME) -> dict:
    """
    Phase 2: generate LaTeX patches, backup, apply, compile.
    Auto-reverts if compilation fails.

    Returns dict with keys: success, done_summary, pdf_path, error
    """
    resume_tex = resume_path.read_text(encoding="utf-8")
    prompt = _EXECUTE_PROMPT.format(
        plan_summary=plan_summary,
        message=message,
        resume_tex=resume_tex,
    )
    raw = _strip_fences(ask_claude(prompt))

    try:
        result = _parse_json_response(raw)
    except json.JSONDecodeError:
        return {
            "success": False,
            "done_summary": "",
            "pdf_path": None,
            "error": "Claude returned invalid JSON. Please try again.",
        }

    patches = result.get("patches", [])
    if not patches:
        return {
            "success": False,
            "done_summary": "",
            "pdf_path": None,
            "error": "No changes were generated for this request.",
        }

    # Validate every patch exists before touching anything
    for p in patches:
        if p.get("old", "") not in resume_tex:
            return {
                "success": False,
                "done_summary": "",
                "pdf_path": None,
                "error": (
                    "Could not locate the following text in the resume to replace:\n"
                    + str(p.get("old", ""))[:140]
                ),
            }

    # Backup before any changes
    backup_path = _next_backup_path(resume_path)
    shutil.copy2(resume_path, backup_path)

    # Apply all patches
    patched = resume_tex
    for p in patches:
        patched = patched.replace(p["old"], p["new"], 1)
    resume_path.write_text(patched, encoding="utf-8")

    # Compile — revert automatically on failure
    try:
        pdf_path = compile_tex(str(resume_path))
    except Exception as exc:
        shutil.copy2(backup_path, resume_path)
        return {
            "success": False,
            "done_summary": "",
            "pdf_path": None,
            "error": f"Compilation failed — changes reverted automatically.\n{exc}",
        }

    return {
        "success": True,
        "done_summary": result.get("done_summary", "Changes applied successfully."),
        "pdf_path": pdf_path,
        "error": None,
    }


def undo(resume_path: Path = _DEFAULT_RESUME) -> dict:
    """
    Revert a resume's `.tex` file to its most recent backup and recompile.

    Returns dict with keys: success, summary, pdf_path
    """
    backups_dir = _backups_dir(resume_path)
    backups_dir.mkdir(parents=True, exist_ok=True)
    backups = sorted(backups_dir.glob("v*.tex"))
    if not backups:
        return {
            "success": False,
            "summary": "Nothing to undo — no backups found.",
            "pdf_path": None,
        }

    latest = backups[-1]
    shutil.copy2(latest, resume_path)
    latest.unlink()

    try:
        pdf_path = compile_tex(str(resume_path))
    except Exception as exc:
        return {
            "success": False,
            "summary": f"File reverted but compilation failed: {exc}",
            "pdf_path": None,
        }

    return {
        "success": True,
        "summary": f"Reverted to backup {latest.name}. Resume restored.",
        "pdf_path": pdf_path,
    }
