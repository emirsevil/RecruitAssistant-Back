"""
routers/generation.py
─────────────────────
API endpoints for AI-powered CV and Cover Letter generation.
Supports Streaming SSE the raw LaTeX generation, and a discrete
compilation endpoint to turn LaTeX into PDF and persist to DB.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import CoverLetter, CV, Workspace
from schemas.generation import (
    GenerateCVRequest,
    GenerateCoverLetterRequest,
    CompileLatexRequest,
    CompileResponse,
    AnalyzeCVRequest,
    ATSAnalysisResponse,
    ImproveSectionRequest,
    ImproveSectionResponse,
    ParseCVResponse,
)
from services.ai_generator import (
    analyze_cv,
    generate_cv_latex_stream,
    generate_cover_letter_latex_stream,
    compile_latex_to_pdf,
    extract_cv_text,
    extract_cv_text_with_raw,
    improve_section,
    parse_cv_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["AI Generation"])


# ──────────────────────────────────────────────
#  POST /api/parse-cv
# ──────────────────────────────────────────────
@router.post("/parse-cv", response_model=ParseCVResponse)
async def api_parse_cv(
    file: UploadFile = File(...),
):
    """
    Extract and normalize source CV text for upload-and-tailor mode.
    Structured fields are returned for backward compatibility, but the main
    CV Studio upload flow treats the extracted text as the source of truth.
    """
    filename = file.filename or "uploaded-cv"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        extracted_text, source_type, raw_extracted_text = extract_cv_text_with_raw(
            file_bytes=contents,
            filename=filename,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("CV parsing failed")
        raise HTTPException(status_code=500, detail="Could not parse this CV file.") from exc

    cv_data, warnings, quality = parse_cv_text(extracted_text)
    analysis = analyze_cv(cv_data, "", quality)

    return ParseCVResponse(
        cvData=cv_data,
        warnings=warnings,
        analysis=analysis,
        quality=quality,
        extractedTextPreview=extracted_text[:1200],
        extractedText=extracted_text[:30000],
        rawExtractedText=raw_extracted_text[:30000],
        sourceName=filename,
        sourceType=source_type,
    )


# ──────────────────────────────────────────────
#  POST /api/analyze-cv
# ──────────────────────────────────────────────
@router.post("/analyze-cv", response_model=ATSAnalysisResponse)
def api_analyze_cv(request: AnalyzeCVRequest):
    """
    Estimate ATS readiness, role match, and missing skill signals for the
    current editable CV state and target job description.
    """
    return analyze_cv(
        cv_data=request.cvData.model_dump(),
        job_description=request.job_description,
        quality=request.quality.model_dump() if request.quality else None,
    )


# ──────────────────────────────────────────────
#  POST /api/improve-section
# ──────────────────────────────────────────────
@router.post("/improve-section", response_model=ImproveSectionResponse)
def api_improve_section(request: ImproveSectionRequest):
    """
    Return section-level AI review notes. Suggestions are constrained to the
    supplied CV data and job description to avoid fabricated experience.
    """
    return improve_section(
        section_name=request.section_name,
        cv_data=request.cvData.model_dump(),
        job_description=request.job_description,
        instructions=request.instructions,
    )


# ──────────────────────────────────────────────
#  POST /api/generate-cv (Streaming)
# ──────────────────────────────────────────────
@router.post("/generate-cv")
def api_generate_cv(
    request: GenerateCVRequest,
):
    """
    Generate a targeted CV using AI (Streaming).
    Yields plain text chunks of raw LaTeX.
    """
    # Simply return a StreamingResponse that pulls from the generator
    return StreamingResponse(
        generate_cv_latex_stream(
            candidate_profile=request.candidate_profile.model_dump() if request.candidate_profile else None,
            job_description=request.job_description,
            raw_cv_text=request.raw_cv_text,
            additional_instructions=request.additional_instructions,
        ),
        media_type="text/event-stream"
    )


# ──────────────────────────────────────────────
#  POST /api/generate-cover-letter (Streaming)
# ──────────────────────────────────────────────
@router.post("/generate-cover-letter")
def api_generate_cover_letter(
    request: GenerateCoverLetterRequest,
):
    """
    Generate a targeted Cover Letter using AI (Streaming).
    Yields plain text chunks of raw LaTeX.
    """
    return StreamingResponse(
        generate_cover_letter_latex_stream(
            candidate_profile=request.candidate_profile.model_dump() if request.candidate_profile else None,
            job_description=request.job_description,
            raw_cv_text=request.raw_cv_text,
            additional_instructions=request.additional_instructions,
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
                    db.commit()
                    db.refresh(db_cv)
                    cv_id = db_cv.id
            else:
                # Create brand new CV entry and link it
                db_cv = CV(
                    user_id=workspace.user_id,
                    latex_content=request.latex_content,
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
