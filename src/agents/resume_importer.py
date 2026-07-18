"""Resume Importer Agent — turns an uploaded resume (PDF, Word, LaTeX,
Markdown, or plain text) into a LaTeX resume that uses this app's template
macros, so it can immediately be chat-edited and compiled like any other
resume identity.
"""

import io
import re
import sys
from pathlib import Path

import docx
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent.parent))
from claude_client import ask_claude

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".tex", ".txt", ".md"}

_TEXT_TO_TEX_PROMPT = """The text below was extracted from someone's resume (originally a PDF or \
Word document, so spacing/line-breaks may be messy, and section boundaries may not be obvious). \
Convert it directly into a LaTeX resume body — do not invent, embellish, or drop any factual \
content (dates, company names, technologies, numbers).

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
  ... one-paragraph summary (write one concise sentence from the rest of the content if the \
source has none — don't leave it empty) ...

  \\vspace{{8pt}}

  % === TECHNICAL SKILLS ===
  \\section*{{Technical Skills}}
  \\begin{{skills}}
    ...
  \\end{{skills}}

  % === EXPERIENCE ===
  \\section{{Experience}}
  ... one \\jobheading per role, each followed by \\projectheading/\\bulletpoints/\\techline \
blocks for that role's work ...

  \\vspace{{8pt}}
  % === PROJECTS (only if the source has standalone projects not tied to a job) ===
  \\section{{Projects}}
  ...

  \\vspace{{8pt}}
  % === EDUCATION ===
  \\section{{Education}}
  ...

  \\vspace{{8pt}}
  \\end{{document}}

Return ONLY the LaTeX body (\\begin{{document}} … \\end{{document}}). No fences. No explanation.

EXTRACTED RESUME TEXT:
{text}
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


def _extract_pdf_text(data: bytes) -> str:
    """Extract plain text from every page of a PDF."""
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(data: bytes) -> str:
    """Extract plain text from every paragraph of a Word document."""
    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)


def extract_text(data: bytes, filename: str) -> str:
    """Extract plain text from an uploaded resume file, based on its extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(data)
    if ext == ".docx":
        return _extract_docx_text(data)
    if ext in (".txt", ".md"):
        return data.decode("utf-8")
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")


def raw_text_to_tex(raw_text: str, template_tex: str) -> str:
    """Convert raw resume text directly into LaTeX using the app's macros, in
    a single Claude call. Preserves `template_tex`'s preamble byte-for-byte;
    only the body is generated."""
    preamble, _ = _split_preamble(template_tex)
    raw = ask_claude(_TEXT_TO_TEX_PROMPT.format(text=raw_text))
    body = _strip_fences(raw)
    if not body.startswith(r"\begin{document}"):
        idx = body.find(r"\begin{document}")
        if idx != -1:
            body = body[idx:]
    return preamble + body


def import_resume_tex(data: bytes, filename: str, template_tex: str) -> str:
    """Convert an uploaded resume file's bytes into LaTeX using the app's macros.

    A `.tex` upload is used as-is (already in the target format). Every other
    supported format is extracted to plain text and converted directly to
    LaTeX in one Claude call — skipping the Markdown intermediate step the
    Resume Editor tab uses, since that step only exists there for a human to
    read/edit and would otherwise double the wait for no benefit here.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")
    if ext == ".tex":
        return data.decode("utf-8")

    raw_text = extract_text(data, filename)
    if not raw_text.strip():
        raise ValueError(
            "No readable text found in this file — if it's a scanned PDF, try a text-based export."
        )
    return raw_text_to_tex(raw_text, template_tex)
