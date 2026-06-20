import re
import json
from pathlib import Path


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_tex(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_preamble(tex: str) -> str:
    match = re.search(r"(\\documentclass.*?\\begin\{document\})", tex, re.DOTALL)
    return match.group(1) if match else ""


def extract_profile(tex: str) -> str:
    """Block between \\begin{document} and the first \\header{} — name, title, contact."""
    match = re.search(r"\\begin\{document\}(.*?)(?=\\header\{)", tex, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_sections(tex: str) -> dict:
    """Return ordered dict of {section_name: raw_latex_content}."""
    pattern = r"\\header\{([^}]+)\}(.*?)(?=\\header\{|\\end\{document\})"
    matches = re.findall(pattern, tex, re.DOTALL)
    return {name.strip(): content.strip() for name, content in matches}


def strip_latex(text: str) -> str:
    """Convert LaTeX markup to plain text for AI consumption."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove comment lines (% through end of line, handles %%%%%... blocks)
    text = re.sub(r"%[^\n]*", "", text)
    # LaTeX line breaks → space
    text = re.sub(r"\\\\", " ", text)
    # Escaped special chars
    text = re.sub(r"\\&", "&", text)
    text = re.sub(r"\\%", "%", text)
    # en-dash: both LaTeX -- and \-- forms → plain hyphen (safe for all encodings)
    text = re.sub(r"\\?--", "-", text)
    # Unwrap formatting commands — keep inner text
    for cmd in ["textbf", "textit", "emph", "underline", "textsc", "textrm", "sl"]:
        text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"\1", text)
    # href — keep display text only
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    # spacing / layout commands with args
    text = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", " ", text)
    # itemize options like \itemsep -3pt or \topsep 0pt
    text = re.sub(r"\\(itemsep|topsep|parsep|partopsep)\s+-?\d+\w+", "", text)
    # bare layout commands
    text = re.sub(r"\\(hfill|raggedright|noindent|lineunder|bull|newline)\b", " ", text)
    # list items
    text = re.sub(r"\\item\[\]", "\n- ", text)
    text = re.sub(r"\\item\b", "\n- ", text)
    # environments
    text = re.sub(r"\\(begin|end)\{[^}]*\}", "", text)
    # remaining commands with braced args
    text = re.sub(r"\\[a-zA-Z]+\*?\{[^}]*\}", "", text)
    # remaining bare commands
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)
    # leftover braces and lone backslashes
    text = re.sub(r"[{}\$\\]", "", text)
    # collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_resume(resume_path: str = None) -> dict:
    """
    Parse the master LaTeX resume.

    Returns:
        preamble   : str  — LaTeX preamble (\\documentclass … \\begin{document})
        profile    : str  — raw LaTeX profile block (name / contact)
        sections   : dict — {section_name: raw_latex}
        plain_text : str  — full resume as plain text (for AI keyword analysis)
        raw_tex    : str  — original file contents
    """
    if resume_path is None:
        resume_path = _load_config()["resume_path"]

    tex = _read_tex(resume_path)
    sections = extract_sections(tex)

    plain_parts = []
    for name, content in sections.items():
        plain_parts.append(f"=== {name} ===\n{strip_latex(content)}")

    return {
        "preamble": extract_preamble(tex),
        "profile": extract_profile(tex),
        "sections": sections,
        "plain_text": "\n\n".join(plain_parts),
        "raw_tex": tex,
    }


if __name__ == "__main__":
    data = parse_resume()
    print("Sections detected:", list(data["sections"].keys()))
    print("\n" + "=" * 60)
    print("PLAIN TEXT PREVIEW")
    print("=" * 60)
    print(data["plain_text"])
