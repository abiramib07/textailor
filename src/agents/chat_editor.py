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
_RESUME = _ROOT / "resume" / "main.tex"
_BACKUPS = _ROOT / "inputs" / "backups"

_PLAN_PROMPT = """You are a resume editor assistant. The user wants to modify their LaTeX resume.

Analyse the request and return ONLY a raw JSON object (no markdown fences, no explanation outside JSON):
{{
  "intent_type": "layout-change | content-remove | content-shorten | content-rewrite | add-content | unknown",
  "summary": "One clear sentence describing exactly what you will do",
  "changes_preview": [
    "Human-readable description of specific change 1",
    "Human-readable description of specific change 2"
  ],
  "questions": [],
  "confidence": "high | medium | low"
}}

If the request is ambiguous (confidence low or medium), put clarifying questions in "questions" and leave changes_preview empty.
Do NOT generate any LaTeX. Just explain the plan in plain English.

USER REQUEST:
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
- "old" must be a character-perfect verbatim substring copied directly from resume.tex — no alterations
- "new" must use only existing macros: \\projectheading{{}}, \\bulletpoints{{}}, \\bulletitem{{}}, \\techline{{}}, \\jobheading{{}}, \\textbf{{}}
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


def _next_backup_path() -> Path:
    _BACKUPS.mkdir(parents=True, exist_ok=True)
    existing = sorted(_BACKUPS.glob("v*.tex"))
    n = len(existing) + 1
    return _BACKUPS / f"v{n}.tex"


def plan(message: str) -> dict:
    """
    Phase 1: analyse the user's request and return a plain-English plan.
    No changes are made to the resume.

    Returns dict with keys: intent_type, summary, changes_preview, questions, confidence, plan_id (added by caller)
    """
    resume_tex = _RESUME.read_text(encoding="utf-8")
    prompt = _PLAN_PROMPT.format(message=message, resume_tex=resume_tex)
    raw = _strip_fences(ask_claude(prompt))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "intent_type": "unknown",
            "summary": "Could not analyse the request — please rephrase it.",
            "changes_preview": [],
            "questions": [],
            "confidence": "low",
        }


def execute(message: str, plan_summary: str) -> dict:
    """
    Phase 2: generate LaTeX patches, backup, apply, compile.
    Auto-reverts if compilation fails.

    Returns dict with keys: success, done_summary, pdf_path, error
    """
    resume_tex = _RESUME.read_text(encoding="utf-8")
    prompt = _EXECUTE_PROMPT.format(
        plan_summary=plan_summary,
        message=message,
        resume_tex=resume_tex,
    )
    raw = _strip_fences(ask_claude(prompt))

    try:
        result = json.loads(raw)
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
    backup_path = _next_backup_path()
    shutil.copy2(_RESUME, backup_path)

    # Apply all patches
    patched = resume_tex
    for p in patches:
        patched = patched.replace(p["old"], p["new"], 1)
    _RESUME.write_text(patched, encoding="utf-8")

    # Compile — revert automatically on failure
    try:
        pdf_path = compile_tex(str(_RESUME))
    except Exception as exc:
        shutil.copy2(backup_path, _RESUME)
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


def undo() -> dict:
    """
    Revert resume/main.tex to the most recent backup and recompile.

    Returns dict with keys: success, summary, pdf_path
    """
    _BACKUPS.mkdir(parents=True, exist_ok=True)
    backups = sorted(_BACKUPS.glob("v*.tex"))
    if not backups:
        return {"success": False, "summary": "Nothing to undo — no backups found.", "pdf_path": None}

    latest = backups[-1]
    shutil.copy2(latest, _RESUME)
    latest.unlink()

    try:
        pdf_path = compile_tex(str(_RESUME))
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
