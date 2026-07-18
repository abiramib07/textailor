"""Compiles a .tex file to PDF via pdflatex, locating the executable across
common MiKTeX install locations on Windows.
"""

import os
import shutil
import subprocess
from pathlib import Path


def _find_pdflatex() -> str:
    """Return path to pdflatex or raise if not found."""
    exe = shutil.which("pdflatex")
    if exe:
        return exe
    # MiKTeX default install location on Windows
    candidates = [
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""), r"Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"
        ),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("pdflatex not found. Install MiKTeX from miktex.org/download")


def compile_tex(tex_path: str) -> str:
    """
    Compile .tex → .pdf using pdflatex (run twice for stable output).
    Returns path to the generated PDF.
    Raises RuntimeError on compile failure (log saved alongside .tex).
    """
    resolved_tex_path = Path(tex_path).resolve()
    out_dir = resolved_tex_path.parent
    pdflatex = _find_pdflatex()

    cmd = [
        pdflatex,
        "-interaction=nonstopmode",
        "--enable-installer",  # MiKTeX: auto-download missing packages
        f"-output-directory={out_dir}",
        str(resolved_tex_path),
    ]

    for run in range(2):
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(out_dir),
        )
        if result.returncode != 0 and run == 1:
            log_path = resolved_tex_path.with_suffix(".log")
            error_snippet = _extract_error(result.stdout)
            raise RuntimeError(f"pdflatex failed.\nError: {error_snippet}\nFull log: {log_path}")

    pdf_path = resolved_tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"PDF not produced at {pdf_path}")
    return str(pdf_path)


def _extract_error(log: str) -> str:
    """Pull the first LaTeX error line from pdflatex output."""
    for line in log.splitlines():
        if line.startswith("!"):
            return line
    return log[-300:] if len(log) > 300 else log
