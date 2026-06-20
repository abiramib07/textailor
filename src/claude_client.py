import subprocess
import sys


def ask_claude(prompt: str) -> str:
    """
    Call Claude Code CLI with a prompt and return the text response.
    Uses the logged-in Claude Pro subscription — no API key needed.
    """
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"[claude_client] stderr: {result.stderr.strip()}", file=sys.stderr)
        raise RuntimeError(f"Claude CLI exited with code {result.returncode}")
    return result.stdout.strip()
