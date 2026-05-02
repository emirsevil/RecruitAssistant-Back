"""
routers/generation.py
─────────────────────
API endpoints for AI-powered CV and Cover Letter generation.
Supports Streaming SSE the raw LaTeX generation, and a discrete
compilation endpoint to turn LaTeX into PDF and persist to DB.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import CoverLetter, CV, Workspace
from schemas.generation import (
    GenerateCVRequest,
    GenerateCoverLetterRequest,
    CompileLatexRequest,
    CompileResponse,
)
from services.ai_generator import (
    generate_cv_latex_stream,
    generate_cover_letter_latex_stream,
    compile_latex_to_pdf,
)
from routers.auth import get_current_user
import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["AI Generation"])


# ──────────────────────────────────────────────
#  POST /api/generate-cv (Streaming)
# ──────────────────────────────────────────────
@router.post("/generate-cv")
def api_generate_cv(
    request: GenerateCVRequest,
    current_user: models.User = Depends(get_current_user)
):
    """
    Generate a targeted CV using AI (Streaming).
    Yields plain text chunks of raw LaTeX.
    """
    # Simply return a StreamingResponse that pulls from the generator
    return StreamingResponse(
        generate_cv_latex_stream(
            candidate_profile=request.candidate_profile.model_dump(),
            job_description=request.job_description,
            special_instructions=request.special_instructions,
            output_language=request.output_language,
        ),
        media_type="text/event-stream"
    )


# ──────────────────────────────────────────────
#  POST /api/generate-cover-letter (Streaming)
# ──────────────────────────────────────────────
@router.post("/generate-cover-letter")
def api_generate_cover_letter(
    request: GenerateCoverLetterRequest,
    current_user: models.User = Depends(get_current_user)
):
    """
    Generate a targeted Cover Letter using AI (Streaming).
    Yields plain text chunks of raw LaTeX.
    """
    return StreamingResponse(
        generate_cover_letter_latex_stream(
            candidate_profile=request.candidate_profile.model_dump(),
            job_description=request.job_description,
            special_instructions=request.special_instructions,
            output_language=request.output_language,
        ),
        media_type="text/event-stream"
    )


# ──────────────────────────────────────────────
#  POST /api/compile-latex
# ──────────────────────────────────────────────
@router.post("/compile-latex", response_model=CompileResponse)
def api_compile_latex(
    request: CompileLatexRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Takes raw LaTeX content (whether originally from AI or manually edited),
    compiles it to PDF, and optionally saves it to the database.
    Returns { pdf_base64, cv_id, cover_letter_id }
    """
    workspace = None
    if request.workspace_id is not None:
        workspace = db.query(Workspace).filter(Workspace.id == request.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace bulunamadı")
        if workspace.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    # Step 1: Compile the provided LaTeX to PDF via Tectonic
    pdf_base64 = compile_latex_to_pdf(request.latex_content)

    # Step 2: Persist to DB if a workspace is configured
    cv_id = None
    cover_letter_id = None
    
    if workspace:
        if request.document_type == "cv":
            # Check if there is already a generated CV linked to this workspace
            if workspace.generated_cv_id:
                # Update existing CV entry
                db_cv = db.query(CV).filter(CV.id == workspace.generated_cv_id).first()
                if db_cv:
                    db_cv.latex_content = request.latex_content
                    db_cv.parsed_data = request.cv_data
                    db.commit()
                    db.refresh(db_cv)
                    cv_id = db_cv.id
            else:
                # Create brand new CV entry and link it
                db_cv = CV(
                    user_id=workspace.user_id,
                    latex_content=request.latex_content,
                    parsed_data=request.cv_data,
                    is_base_cv=False,
                )
                db.add(db_cv)
                db.flush()
                cv_id = db_cv.id
                workspace.generated_cv_id = cv_id
                db.commit()
            
        elif request.document_type == "cover_letter":
            # For simplicity, we just create a new cover letter record,
            # or update the most recent one for this workspace.
            db_cover_letter = db.query(CoverLetter).filter(
                CoverLetter.workspace_id == workspace.id
            ).order_by(CoverLetter.created_at.desc()).first()

            if db_cover_letter:
                db_cover_letter.content = request.latex_content
                db_cover_letter.latex_content = request.latex_content
                db.commit()
                db.refresh(db_cover_letter)
                cover_letter_id = db_cover_letter.id
            else:
                db_cover_letter = CoverLetter(
                    workspace_id=workspace.id,
                    content=request.latex_content,
                    latex_content=request.latex_content,
                )
                db.add(db_cover_letter)
                db.commit()
                db.refresh(db_cover_letter)
                cover_letter_id = db_cover_letter.id

        else:
            raise HTTPException(
                status_code=400, 
                detail="document_type must be either 'cv' or 'cover_letter'."
            )

    return CompileResponse(
        pdf_base64=pdf_base64,
        cv_id=cv_id,
        cover_letter_id=cover_letter_id,
    )
