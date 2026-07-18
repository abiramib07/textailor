"""Patches rewritten section content back into the original resume's LaTeX,
preserving everything outside the rewritten sections untouched.
"""

import re
from pathlib import Path
from re import Match


def patch(
    original_tex: str,
    rewritten_sections: dict,
    original_sections: dict,
) -> str:
    """
    Replace section bodies in the original .tex with rewritten content.
    Identifies each section's block by its \\header{} marker and replaces
    everything up to (but not including) the next \\header{} or \\end{document}.
    """
    result = original_tex

    for name, new_content in rewritten_sections.items():
        if name not in original_sections:
            continue

        # Match \section{Name} or \section*{Name} + body up to next section / end
        header_pattern = (
            r"(\\section\*?\{" + re.escape(name) + r"\})"
            r"(.*?)"
            r"(?=\\section\*?\{|\\end\{document\})"
        )
        _new = new_content.strip()

        def _replace(m: Match, new: str = _new) -> str:
            return m.group(1) + "\n" + new + "\n\n"

        updated = re.sub(
            header_pattern,
            _replace,
            result,
            count=1,
            flags=re.DOTALL,
        )
        if updated != result:
            result = updated

    return result


def write_tailored_tex(
    original_tex: str,
    rewritten_sections: dict,
    original_sections: dict,
    output_path: str,
) -> str:
    """Patch and write the tailored .tex file. Returns the output path."""
    patched = patch(original_tex, rewritten_sections, original_sections)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(patched)
    return output_path
