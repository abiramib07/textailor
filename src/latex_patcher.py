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


def _latex_escape(text: str) -> str:
    """Escape the handful of LaTeX-special characters plausible in a
    JD-derived keyword phrase (job posts aren't LaTeX-aware)."""
    return text.replace("&", "\\&").replace("%", "\\%").replace("#", "\\#").replace("_", "\\_")


# Category name -> terms that indicate a JD-derived keyword belongs there.
# Ordered by specificity: more specific categories (e.g. a named framework
# list) are checked before broader ones so a keyword mentioning both takes
# the more specific home.
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "AI Frameworks",
        (
            "tensorflow",
            "pytorch",
            "scikit-learn",
            "scikit learn",
            "keras",
            "ml framework",
            "machine learning framework",
            "hugging face",
        ),
    ),
    (
        "Agentic Architectures",
        ("agentic", "multi-agent", "multi agent", "mcp", "a2a"),
    ),
    (
        "Generative AI / NLP",
        (
            "nlp",
            "natural language",
            "tokeniz",
            "vectoriz",
            "semantic analysis",
            "retrieval-augmented",
            "retrieval augmented",
            "rag",
            "genai",
            "generative ai",
            "large language model",
            "llm",
            "prompt engineering",
            "named entity",
            "summarization",
        ),
    ),
    (
        "DevOps / Cloud",
        (
            "aws",
            "azure",
            "gcp",
            "google cloud",
            "docker",
            "kubernetes",
            "ci/cd",
            "mlops",
            "model lifecycle",
            "model monitoring",
            "model retraining",
            "model performance",
            "model deployment",
            "deployment pipeline",
        ),
    ),
    (
        "Data & Vector Stores",
        (
            "database",
            "vector store",
            "postgres",
            "mongo",
            "elasticsearch",
            "redis",
            "faiss",
            "pinecone",
            "chroma",
            "vector db",
        ),
    ),
    (
        "Data Processing & Analysis",
        (
            "data collection",
            "exploratory data analysis",
            "eda",
            "data preparation",
            "data cleaning",
            "data preprocessing",
            "data wrangling",
        ),
    ),
    (
        "Data & Visualization",
        ("visualization", "matplotlib", "seaborn", "plotly", "dashboard"),
    ),
    (
        "Backend & APIs",
        ("rest api", "restful", "fastapi", "flask", "microservices"),
    ),
]


def _term_matches(text: str, term: str) -> bool:
    """Case-insensitive match requiring `term` to start at a word boundary
    but not necessarily end at one, so short stems like "tokeniz" still
    match "tokenization". A leading-boundary-only check also sidesteps the
    classic false positive where a short term appears mid-word in unrelated
    text (e.g. "rag" inside "average", "ner" inside "generative")."""
    return re.search(rf"\b{re.escape(term.lower())}", text.lower()) is not None


def _categorize_skill(keyword: str) -> str:
    """Best-effort Technical Skills category for a JD-derived keyword
    phrase. Falls back to a generic "Additional Skills" bucket when no
    rule matches."""
    for category, terms in _CATEGORY_RULES:
        if any(_term_matches(keyword, term) for term in terms):
            return category
    return "Additional Skills"


def add_skills_row(section_tex: str, keywords: list[str]) -> str:
    """Fold the given JD-derived keywords into a Technical Skills section's
    raw LaTeX, grouping each keyword under the most relevant category
    instead of dumping everything into one catch-all row: a keyword is
    appended to an existing `\\skillrow` whose heading matches its category
    if one is already present, otherwise a new, properly-named row is
    inserted before the closing `\\end{tabularx}`. Used for the fast,
    deterministic "add these missing keywords to my skills table" action —
    no AI rewrite involved, so it can't invent skills the candidate didn't
    select."""
    if not keywords:
        return section_tex

    grouped: dict[str, list[str]] = {}
    for kw in keywords:
        grouped.setdefault(_categorize_skill(kw), []).append(kw)

    existing_rows = {
        m.group(1).strip().lower(): m
        for m in re.finditer(r"\\skillrow\{([^}]*)\}\{([^}]*)\}", section_tex)
    }

    updated = section_tex
    new_rows: list[str] = []
    for category, kws in grouped.items():
        escaped_new = ", ".join(_latex_escape(kw) for kw in kws)
        match = existing_rows.get(category.lower())
        if match:
            old_row_text = match.group(0)
            old_items = match.group(2)
            new_row_text = old_row_text.replace(
                "{" + old_items + "}",
                "{" + old_items + ", " + escaped_new + "}",
                1,
            )
            updated = updated.replace(old_row_text, new_row_text, 1)
        else:
            category_escaped = _latex_escape(category)
            new_rows.append(f"    \\skillrow{{{category_escaped}}}{{{escaped_new}}}\n")

    if new_rows:
        block = "".join(new_rows)
        if "\\end{tabularx}" in updated:
            updated = updated.replace("\\end{tabularx}", block + "\\end{tabularx}", 1)
        else:
            updated = updated.rstrip() + "\n" + block

    return updated
