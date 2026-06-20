import subprocess
import sys
import os

# Claude Code CLI — installed via npm, requires cmd /c on Windows for .cmd files
_CLAUDE_CMD = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")


def ask_claude(prompt: str) -> str:
    """
    Pipe prompt to Claude Code CLI via stdin (avoids Windows cmd quoting limits).
    Uses the logged-in Claude Pro subscription — no API key needed.
    """
    result = subprocess.run(
        ["cmd", "/c", _CLAUDE_CMD, "--print", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"[claude_client] stderr: {result.stderr.strip()}", file=sys.stderr)
        raise RuntimeError(f"Claude CLI exited with code {result.returncode}")
    return result.stdout.strip()


if __name__ == "__main__":
    print(ask_claude("Reply with exactly three words: PIPELINE IS CONNECTED"))
