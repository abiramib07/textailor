"""Thin wrapper around the Claude Code CLI, used by every agent to send a
prompt and get back plain text. Requires the user's own Claude Pro
subscription to be logged in via the CLI — no API key needed.
"""

import os
import subprocess
import sys

# Claude Code CLI — installed via npm, requires cmd /c on Windows for .cmd files
_CLAUDE_CMD = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")


def ask_claude(prompt: str) -> str:
    """
    Pipe prompt to Claude Code CLI via stdin (avoids Windows cmd quoting limits).
    Uses the logged-in Claude Pro subscription — no API key needed.
    """
    try:
        result = subprocess.run(
            ["cmd", "/c", _CLAUDE_CMD, "--print", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,  # 5 min hard cap per section call
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Claude CLI timed out after 300s — prompt may be too large") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        print(f"[claude_client] stderr: {stderr}", file=sys.stderr)
        raise RuntimeError(f"Claude CLI exited with code {result.returncode}: {stderr}")
    return result.stdout.strip()


if __name__ == "__main__":
    print(ask_claude("Reply with exactly three words: PIPELINE IS CONNECTED"))
