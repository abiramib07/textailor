"""
Resume Editor Agent — processes inputs/pending-edits.md and patches resume/main.tex.

Run standalone:   python src/agents/editor.py
Called by main:   from agents.editor import apply_pending_edits; apply_pending_edits(config)

Workflow:
  1. Read inputs/pending-edits.md — skip if blank/comments-only
  2. Ask Claude to analyse: what type of edit, target position, generate LaTeX
  3. Show the proposed change and ask user to confirm (Y/n)
  4. If confirmed, patch resume/main.tex
  5. Archive the processed edit to inputs/processed/YYYY-MM-DD-<slug>.md
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

_ROOT = Path(__file__).parent.parent.parent
_PENDING = _ROOT / "inputs" / "pending-edits.md"
_PROCESSED = _ROOT / "inputs" / "processed"
_RESUME = _ROOT / "resume" / "main.tex"

_COMMENT_RE = re.compile(r"^#.*$", re.MULTILINE)

_ANALYSE_PROMPT = """You are an expert resume LaTeX editor.

You will receive:
1. RAW EDIT CONTENT — raw text pasted by the user describing a change to their resume
2. CURRENT RESUME TEX — the full LaTeX source of the resume

Your job:
A. Detect the edit type: add-project | update-project | add-skill | update-summary | other
B. Identify the exact insertion/replacement point in the resume (copy the exact surrounding LaTeX lines)
C. Generate the complete, properly escaped LaTeX block for the edit
D. Return a JSON object (no markdown fences, just raw JSON) with this shape:

{{
  "edit_type": "add-project",
  "target_description": "Under KGISL Generative AI Developer, before AI-Powered Conversational Platform",
  "ambiguities": [],
  "insert_before": "\\\\projectheading{{AI-Powered Conversational Platform",
  "latex_block": "\\\\projectheading{{...}}\\n\\\\bulletpoints{{...}}\\n\\\\techline{{...}}"
}}

LaTeX escaping rules you MUST follow:
- & → \\&
- → (arrow) → $\\rightarrow$
- % → \\%
- $ → \\$
- # → \\#
- _ in running text → \\_
- -- flags like --resume → -{{}}-resume
- Use \\textbf{{}} for bold, do NOT invent new macros
- Use only the macros already in the file: \\projectheading{{}}, \\bulletpoints{{}}, \\bulletitem{{}}, \\techline{{}}

If there is genuine ambiguity (e.g., no target company is clear), list it in "ambiguities" as short questions.
If everything is clear, "ambiguities" must be an empty list [].

RAW EDIT CONTENT:
{edit_content}

CURRENT RESUME TEX:
{resume_tex}
"""


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text).strip()


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text[:40]).strip("-").lower()


def _ask_clarifications(questions: list[str]) -> dict[str, str]:
    answers = {}
    print("\n[Editor Agent] Clarifying questions before applying edit:\n")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
        answer = input("     Your answer: ").strip()
        answers[q] = answer
    return answers


def _confirm(proposal: str) -> bool:
    print("\n" + "=" * 60)
    print("PROPOSED RESUME CHANGE")
    print("=" * 60)
    print(proposal)
    print("=" * 60)
    response = input("\nApply this change? [Y/n]: ").strip().lower()
    return response in ("", "y", "yes")


def apply_pending_edits(config: dict | None = None) -> bool:
    """
    Read inputs/pending-edits.md, analyse with Claude, confirm with user, patch resume.
    Returns True if an edit was applied, False if nothing to do.
    """
    if not _PENDING.exists():
        return False

    raw = _PENDING.read_text(encoding="utf-8")
    content = _strip_comments(raw)

    if not content:
        print("[Editor Agent] No pending edits found in inputs/pending-edits.md — skipping.")
        return False

    print("\n[Editor Agent] Pending edit detected — analysing...")

    resume_tex = _RESUME.read_text(encoding="utf-8")

    prompt = _ANALYSE_PROMPT.format(
        edit_content=content,
        resume_tex=resume_tex,
    )

    raw_json = ask_claude(prompt)

    # Strip accidental markdown fences
    raw_json = re.sub(r"^```[a-z]*\n?", "", raw_json.strip(), flags=re.MULTILINE)
    raw_json = re.sub(r"```$", "", raw_json.strip(), flags=re.MULTILINE).strip()

    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError:
        print(f"[Editor Agent] Claude returned non-JSON output:\n{raw_json}")
        print("[Editor Agent] Edit NOT applied. Check inputs/pending-edits.md and retry.")
        return False

    # Handle clarifications
    if result.get("ambiguities"):
        answers = _ask_clarifications(result["ambiguities"])
        # Re-ask Claude with the answers appended
        clarified_content = (
            content
            + "\n\nClarifications from user:\n"
            + "\n".join(f"Q: {q}\nA: {a}" for q, a in answers.items())
        )
        prompt2 = _ANALYSE_PROMPT.format(edit_content=clarified_content, resume_tex=resume_tex)
        raw_json2 = ask_claude(prompt2)
        raw_json2 = re.sub(r"^```[a-z]*\n?", "", raw_json2.strip(), flags=re.MULTILINE)
        raw_json2 = re.sub(r"```$", "", raw_json2.strip(), flags=re.MULTILINE).strip()
        try:
            result = json.loads(raw_json2)
        except json.JSONDecodeError:
            print("[Editor Agent] Could not parse Claude response after clarifications.")
            return False

    latex_block = result.get("latex_block", "").strip()
    insert_before = result.get("insert_before", "").strip()
    target_desc = result.get("target_description", "unknown position")

    if not latex_block or not insert_before:
        print("[Editor Agent] Claude did not return a complete edit plan. Edit NOT applied.")
        print(f"  Response: {result}")
        return False

    # Confirm with user
    proposal = (
        f"Target : {target_desc}\n"
        f"Action : insert before → {insert_before[:80]}...\n\n"
        f"LaTeX to insert:\n{latex_block}"
    )
    if not _confirm(proposal):
        print("[Editor Agent] Edit cancelled by user.")
        return False

    # Patch the resume
    if insert_before not in resume_tex:
        print(f"[Editor Agent] Could not find insertion point in resume:\n  {insert_before}")
        print("[Editor Agent] Edit NOT applied.")
        return False

    patched = resume_tex.replace(insert_before, latex_block + "\n\n" + insert_before, 1)
    _RESUME.write_text(patched, encoding="utf-8")
    print("[Editor Agent] resume/main.tex patched successfully.")

    # Archive the processed edit
    _PROCESSED.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _slug(content[:60])
    archive_path = _PROCESSED / f"{date_str}-{slug}.md"
    archive_path.write_text(
        f"# Processed Edit — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"**Type:** {result.get('edit_type', 'unknown')}\n"
        f"**Target:** {target_desc}\n\n"
        f"## Raw Input\n\n{content}\n\n"
        f"## Applied LaTeX\n\n```latex\n{latex_block}\n```\n",
        encoding="utf-8",
    )

    # Clear pending-edits.md back to template
    _PENDING.write_text(
        "# Resume Pending Edits\n"
        "# Drop raw content here — the editor agent will analyse, ask clarifying questions if needed,\n"
        "# and insert it into resume/main.tex at the right place.\n"
        "#\n"
        "# Supported edit types (the agent auto-detects):\n"
        "#   - New project entry (paste raw bullet points + tech stack)\n"
        "#   - Update/replace existing project bullets\n"
        "#   - Add or remove a skill\n"
        "#   - Rewrite a summary line\n"
        "#\n"
        "# Optionally hint the target with a header like:\n"
        '#   TARGET: KGISL > Generative AI Developer > before "AI-Powered Conversational Platform"\n'
        "#\n"
        "# Leave blank (or only these comments) when there are no pending edits.\n"
        "# Processed edits are archived to inputs/processed/YYYY-MM-DD-<slug>.md automatically.\n"
        "# ───────────────────────────────────────────────────────────────────────────\n",
        encoding="utf-8",
    )
    print(f"[Editor Agent] Edit archived to {archive_path.name} — pending-edits.md cleared.")
    return True


if __name__ == "__main__":
    applied = apply_pending_edits()
    if not applied:
        sys.exit(0)
    print("\n[Editor Agent] Done. Run the pipeline or compile resume/main.tex to see the result.")
