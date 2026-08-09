"""Parses the master LaTeX resume into its preamble, profile block, and
per-section content, plus a plain-text rendering for Claude prompts.
"""

import json
import re
from pathlib import Path


def _load_config() -> dict:
    """Load config.json from the project root."""
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _read_tex(path: str) -> str:
    """Read a .tex file as UTF-8 text."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_preamble(tex: str) -> str:
    """Return everything from \\documentclass through \\begin{document}."""
    match = re.search(r"(\\documentclass.*?\\begin\{document\})", tex, re.DOTALL)
    return match.group(1) if match else ""


def extract_profile(tex: str) -> str:
    """Header block (name, contact line) — the `center` environment between
    `\\begin{document}` and the first `\\section`. Scoped to just that
    environment (not everything up to the first section) so boilerplate like
    `\\setlength`, comments, and the font-weight hook don't leak into it."""
    match = re.search(r"\\begin\{center\}(.*?)\\end\{center\}", tex, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_contact_fields(profile_tex: str) -> dict[str, str]:
    """Pull structured contact fields (name, phone, email, linkedin, github)
    out of the raw LaTeX header block returned by `extract_profile`. Any
    field not found comes back as an empty string."""
    fields = {"name": "", "phone": "", "email": "", "linkedin": "", "github": ""}

    name_match = re.search(r"\\textbf\{([^}]*)\}", profile_tex)
    if name_match:
        fields["name"] = name_match.group(1).strip()

    hrefs = re.findall(r"\\href\{([^}]*)\}\{([^}]*)\}", profile_tex)
    remainder = profile_tex
    for url, display in hrefs:
        remainder = remainder.replace(f"\\href{{{url}}}{{{display}}}", " ")
        if url.lower().startswith("mailto:"):
            fields["email"] = url[len("mailto:") :].strip() or display.strip()
        elif "linkedin" in url.lower():
            fields["linkedin"] = display.strip() or url.strip()
        elif "github" in url.lower():
            fields["github"] = display.strip() or url.strip()

    if not fields["email"]:
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", profile_tex)
        if email_match:
            fields["email"] = email_match.group(0)

    phone_match = re.search(r"(?<!\d)(\+?\d[\d\-\s]{7,}\d)(?!\d)", remainder)
    if phone_match:
        fields["phone"] = phone_match.group(1).strip()

    return fields


def extract_skill_list(sections: dict) -> list[str]:
    """Flatten the Technical Skills section's `\\skillrow{category}{items}`
    calls into a deduplicated, ordered list of individual skill/tool
    strings — used to cross-reference the resume against interview-prep
    topics, JD-observed keywords, and the application tracker."""
    skills_tex = sections.get("Technical Skills", "")
    if not skills_tex:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for _category, items in re.findall(r"\\skillrow\{([^}]*)\}\{([^}]*)\}", skills_tex):
        items = items.replace("\\&", "&")
        for item in items.split(","):
            skill = item.strip()
            if skill and skill.lower() not in seen:
                seen.add(skill.lower())
                ordered.append(skill)
    return ordered


def extract_sections(tex: str) -> dict:
    """Return ordered dict of {section_name: raw_latex_content}."""
    pattern = r"\\section\*?\{([^}]+)\}(.*?)(?=\\section\*?\{|\\end\{document\})"
    matches = re.findall(pattern, tex, re.DOTALL)
    return {name.strip(): content.strip() for name, content in matches}


def strip_latex(text: str) -> str:
    """Convert LaTeX markup to plain text for AI consumption."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove comment lines (% through end of line, handles %%%%%... blocks) —
    # but NOT an escaped \% (e.g. "85\% answer relevance..."), which is real
    # content, not a comment marker. Without the negative lookbehind, this
    # used to truncate any bullet containing a literal percent (a very common
    # resume metric) at the first \%, silently deleting everything after it
    # on that line.
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)
    # LaTeX line breaks, with an optional [<length>] spacing arg → space
    text = re.sub(r"\\\\(\[[^\]]*\])?", " ", text)
    # Escaped special chars
    text = re.sub(r"\\&", "&", text)
    text = re.sub(r"\\%", "%", text)
    # en-dash: both LaTeX -- and \-- forms → plain hyphen (safe for all encodings)
    text = re.sub(r"\\?--", "-", text)
    # Invisible font-switch bare commands (\selectfont, \bfseries, ...) — strip these
    # BEFORE unwrapping \textbf{...} etc below. Otherwise "\selectfont\textbf{Name}"
    # becomes "\selectfontName" once textbf is unwrapped, and the generic bare-command
    # regex greedily swallows "selectfontName" as a single command name, eating the
    # real text with it.
    text = re.sub(
        r"\\(selectfont|bfseries|itshape|upshape|normalfont|scshape|rmfamily|sffamily|ttfamily|mdseries)\b",
        "",
        text,
    )
    # Unwrap formatting commands — keep inner text. Order matters: this is a
    # single-level unwrap (`[^}]*` doesn't cross nested braces), so each
    # command only unwraps correctly once anything nested INSIDE it has
    # already been flattened to bare text by an earlier pass. That's why
    # `bulletitem` (innermost) comes before `bulletpoints` (its outer
    # wrapper) — a bullet like `\bulletpoints{\bulletitem{Built \textbf{RAG}
    # pipelines}}` needs textbf flattened first, then bulletitem, then
    # bulletpoints, in that order.
    #
    # Without this, every one of this template's structural macros —
    # `\bulletitem`, `\bulletpoints`, `\techline`, `\projectheading` — falls
    # through to the generic "delete any unrecognised \command{...}" cleanup
    # below, which deletes the command AND its content. That used to
    # silently wipe every resume bullet, every "Technologies: ..." line, and
    # every project title from the plain text the recruiter/scorer agents
    # actually see.
    for cmd in [
        "textbf",
        "textit",
        "emph",
        "underline",
        "textsc",
        "textrm",
        "sl",
        "bulletitem",
        "bulletpoints",
        "techline",
        "projectheading",
    ]:
        text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"\1", text)
    # \jobheading{role}{company}{location}{dates} — keep all four fields,
    # space-separated (the generic cleanup below would otherwise drop the
    # role title and mash company/location/dates together with no spacing).
    text = re.sub(r"\\jobheading\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}", r"\1 \2 \3 \4", text)
    # \skillrow{category}{items} — keep the category label alongside its items.
    text = re.sub(r"\\skillrow\{([^}]*)\}\{([^}]*)\}", r"\1: \2", text)
    # href — keep display text only
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    # spacing / layout commands with args
    text = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", " ", text)
    # \fontsize{size}{baselineskip} — two required brace args, drop both
    text = re.sub(r"\\fontsize\{[^}]*\}\{[^}]*\}", "", text)
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


def parse_resume(resume_path: str | None = None) -> dict:
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
    profile = extract_profile(tex)

    plain_parts = []
    profile_text = strip_latex(profile)
    if profile_text:
        plain_parts.append(f"=== Contact Info ===\n{profile_text}")
    for name, content in sections.items():
        plain_parts.append(f"=== {name} ===\n{strip_latex(content)}")

    return {
        "preamble": extract_preamble(tex),
        "profile": profile,
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
