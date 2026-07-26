"""Thin wrapper around the Claude Code CLI, used by every agent to send a
prompt and get back plain text. Requires the user's own Claude Pro
subscription to be logged in via the CLI — no API key needed.
"""

import json
import logging
import os
import subprocess
import time
from collections.abc import Iterator

log = logging.getLogger("textailor.claude_client")

# Claude Code CLI — installed via npm, requires cmd /c on Windows for .cmd files
_CLAUDE_CMD = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")


def ask_claude(prompt: str, allowed_tools: str | None = None, timeout: int = 300) -> str:
    """
    Pipe prompt to Claude Code CLI via stdin (avoids Windows cmd quoting limits).
    Uses the logged-in Claude Pro subscription — no API key needed.

    `allowed_tools` grants access to specific built-in tools (e.g. "WebSearch")
    for agents that need more than plain text generation — otherwise the CLI
    runs with no tool access.
    """
    args = ["cmd", "/c", _CLAUDE_CMD, "--print", "--output-format", "text"]
    if allowed_tools:
        args += ["--allowedTools", allowed_tools]
    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        log.error("Claude CLI timed out after %ds (prompt: %d chars)", timeout, len(prompt))
        raise RuntimeError(
            f"Claude CLI timed out after {timeout}s — prompt may be too large"
        ) from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        log.error("Claude CLI exited with code %d: %s", result.returncode, stderr)
        raise RuntimeError(f"Claude CLI exited with code {result.returncode}: {stderr}")
    return result.stdout.strip()


def stream_claude(prompt: str, allowed_tools: str, timeout: int = 480) -> Iterator[dict]:
    """
    Run the Claude Code CLI in streaming mode, yielding each parsed
    stream-json event as it arrives — lets a caller surface live progress
    (e.g. which web search query is currently running) for long calls
    instead of blocking silently until the final answer.

    The last event yielded is always the CLI's own `{"type": "result", ...}`
    summary, whose `result` field holds the final text (same content
    `ask_claude` would have returned via `--output-format text`).
    """
    args = [
        "cmd",
        "/c",
        _CLAUDE_CMD,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--allowedTools",
        allowed_tools,
    ]
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    deadline = time.monotonic() + timeout
    try:
        for line in proc.stdout:
            if time.monotonic() > deadline:
                proc.kill()
                raise RuntimeError(f"Claude CLI timed out after {timeout}s")
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        proc.stdout.close()

    returncode = proc.wait(timeout=10)
    if returncode != 0:
        stderr = proc.stderr.read().strip() if proc.stderr else ""
        log.error("Claude CLI exited with code %d: %s", returncode, stderr)
        raise RuntimeError(f"Claude CLI exited with code {returncode}: {stderr}")


if __name__ == "__main__":
    print(ask_claude("Reply with exactly three words: PIPELINE IS CONNECTED"))
