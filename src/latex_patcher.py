import re
import shutil
from pathlib import Path


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
        updated = re.sub(
            header_pattern,
            lambda m: m.group(1) + "\n" + _new + "\n\n",
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
