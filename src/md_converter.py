"""
MD ↔ LaTeX converter for the resume editor tab.

tex_to_md(tex_content)              → Markdown (human-editable resume draft)
md_to_tex(md_content, original_tex) → updated LaTeX, preamble preserved exactly
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_client import ask_claude

_TEX_TO_MD = """Convert the following LaTeX resume to clean Markdown for a human editor to read and edit.

Formatting rules:
- # Name  for the candidate name line
- Contact info on the next line: phone | email | linkedin
- ## Section  for top-level sections (Professional Summary, Technical Skills, Experience, Education)
- ### Role @ Company | Date Range  for each job heading
- #### Project Title  for each project under a job
- - bullet text  for each bullet point
- **Tech:** comma, list  for technology lines at the end of each project
- For Technical Skills: keep as  - **Category:** list

Return ONLY the Markdown. No code fences. No explanation.

LATEX RESUME:
{tex}
"""

_MD_TO_TEX_BODY = """Convert the Markdown resume below into a LaTeX document body.

Use ONLY these macros (already defined in the preamble — do not redefine them):
  \\jobheading{{role}}{{date-range}}{{company}}{{location}}
  \\projectheading{{title}}
  \\bulletpoints{{  \\bulletitem{{...}} ... }}
  \\techline{{tech1, tech2, ...}}
  \\section{{Name}} and \\section*{{Name}} for section headings
  \\begin{{skills}} ... \\end{{skills}} with \\item \\textbf{{Category:}} text  for skills

LaTeX escaping (apply in all text):
  &  →  \\&
  %  →  \\%
  #  →  \\#
  →  →  $\\rightarrow$
  --flag  →  -{{}}--flag (prevent ligature)

Required document structure:
  \\begin{{document}}
  \\setlength{{\\parindent}}{{0pt}}

  % === HEADER ===
  \\begin{{center}}
    {{\\fontsize{{24}}{{28}}\\selectfont\\textbf{{NAME}}}} \\\\[3pt]
    {{\\fontsize{{11}}{{13}}\\selectfont phone \\,|\\, email \\,|\\,\\href{{url}}{{link}}}}
  \\end{{center}}
  \\vspace{{6pt}}

  % === PROFESSIONAL SUMMARY ===
  \\section*{{Professional Summary}}
  ... summary text ...

  \\vspace{{8pt}}

  % === TECHNICAL SKILLS ===
  \\section*{{Technical Skills}}
  \\begin{{skills}}
    ...
  \\end{{skills}}

  % === EXPERIENCE ===
  \\section{{Experience}}
  ... job entries ...

  \\vspace{{8pt}}
  % === EDUCATION ===
  \\section{{Education}}
  ...

  \\vspace{{8pt}}

  \\end{{document}}

MARKDOWN TO CONVERT:
{md}

Return ONLY the LaTeX body (\\begin{{document}} … \\end{{document}}). No fences. No explanation.
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _split_preamble(tex: str) -> tuple[str, str]:
    """Return (preamble_up_to_begin_document, body_from_begin_document)."""
    marker = r"\begin{document}"
    idx = tex.find(marker)
    if idx == -1:
        return tex, ""
    return tex[:idx], tex[idx:]


def tex_to_md(tex_content: str) -> str:
    """Convert LaTeX resume → Markdown. Called once to seed resume-content.md."""
    raw = ask_claude(_TEX_TO_MD.format(tex=tex_content))
    return _strip_fences(raw)


def md_to_tex(md_content: str, original_tex: str) -> str:
    """
    Convert Markdown resume → LaTeX.
    Preserves the original preamble byte-for-byte; only the body is regenerated.
    """
    preamble, _ = _split_preamble(original_tex)
    raw = ask_claude(_MD_TO_TEX_BODY.format(md=md_content))
    new_body = _strip_fences(raw)

    # Ensure body starts at \begin{document}
    if not new_body.startswith(r"\begin{document}"):
        idx = new_body.find(r"\begin{document}")
        if idx != -1:
            new_body = new_body[idx:]

    return preamble + new_body
