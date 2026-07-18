"""FastAPI routes for `/api/resumes`: manage multiple resume identities
(your own, or someone else's) that the rest of the app scopes its
generation/history/career data to. Mounted into the main app by `src.api`.
"""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.resume_importer import SUPPORTED_EXTENSIONS, import_resume_tex
from compiler import compile_tex

from .db import (
    create_resume,
    delete_resume,
    get_default_resume,
    get_resume,
    list_resumes,
    update_resume,
)
from .schemas import ResumeUpdate

log = logging.getLogger("textailor.resumes")

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.get("")
def get_resumes() -> dict:
    """List every resume identity, default first."""
    return {"entries": list_resumes()}


@router.post("")
async def post_resume(
    label: str = Form(...),
    owner_name: str = Form(""),
    file: UploadFile = File(...),
) -> dict:
    """Add a new resume identity from an uploaded resume file.

    `.tex` is used as-is; `.pdf`, `.docx`, `.txt`, and `.md` are converted
    into the app's LaTeX template via `agents.resume_importer`. Compiles a
    preview PDF immediately so the new resume can be chat-curated right away.
    """
    if not label.strip():
        raise HTTPException(status_code=400, detail="Give this resume a label")

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type. Use one of: {supported}"
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    template_tex = Path(get_default_resume()["tex_path"]).read_text(encoding="utf-8")
    try:
        tex_content = import_resume_tex(data, filename, template_tex)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not process this file: {exc}") from exc

    resume = create_resume(label, owner_name, tex_content)
    log.info("Resume created  id=%s  label=%s  source=%s", resume["id"], resume["label"], ext)

    compile_warning = None
    try:
        compile_tex(resume["tex_path"])
    except Exception as exc:
        compile_warning = str(exc)
        log.warning("Initial compile failed for new resume %s: %s", resume["id"], exc)

    return {
        "resume": resume,
        "has_pdf": compile_warning is None,
        "compile_warning": compile_warning,
    }


@router.patch("/{resume_id}")
def patch_resume(resume_id: str, req: ResumeUpdate) -> dict:
    """Rename a resume identity or update its owner name."""
    resume = update_resume(resume_id, req.label, req.owner_name)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"resume": resume}


@router.delete("/{resume_id}")
def remove_resume(resume_id: str) -> dict:
    """Delete a non-default resume identity and its files."""
    resume = get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume["is_default"]:
        raise HTTPException(status_code=400, detail="Cannot delete your default resume")
    delete_resume(resume_id)
    return {"ok": True}
