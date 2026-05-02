import base64

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional

from database import get_db
import models
from crud.cv import resolve_user_cv
from routers.auth import get_current_user

router = APIRouter(prefix="/api/cv", tags=["CV Management"])


class BaseCVUpsertPayload(BaseModel):
    parsed_data: Dict[str, Any]
    pdf_base64: Optional[str] = None  # If provided, replaces stored PDF; None leaves it unchanged.


@router.get("/workspace/{workspace_id}/availability")
def cv_availability(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Pre-flight check: does the user have a CV usable for this workspace's HR interview?"""
    workspace = (
        db.query(models.Workspace)
        .filter(models.Workspace.id == workspace_id)
        .first()
    )
    if workspace and workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    parsed, source = resolve_user_cv(db, current_user.id, workspace)
    return {"has_cv": parsed is not None, "source": source}

@router.get("/base")
def get_base_cv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve the user's Base CV parsed JSON data.
    """
    base_cv = db.query(models.CV).filter(
        models.CV.user_id == current_user.id,
        models.CV.is_base_cv == True
    ).first()

    if not base_cv or not base_cv.parsed_data:
        # User hasn't uploaded a base CV yet or it has no parsed data
        return {"parsed_data": None, "has_pdf": False}

    return {"parsed_data": base_cv.parsed_data, "has_pdf": bool(base_cv.original_pdf_b64)}


@router.get("/base/pdf")
def get_base_cv_pdf(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the originally-uploaded base-CV PDF as application/pdf."""
    base_cv = (
        db.query(models.CV)
        .filter(
            models.CV.user_id == current_user.id,
            models.CV.is_base_cv.is_(True),
        )
        .first()
    )
    if not base_cv or not base_cv.original_pdf_b64:
        raise HTTPException(status_code=404, detail="PDF not available for this base CV")

    try:
        pdf_bytes = base64.b64decode(base_cv.original_pdf_b64)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=500, detail="Stored PDF is corrupted")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=base_cv.pdf"},
    )


@router.delete("/base", status_code=204)
def delete_base_cv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete the user's base CV row."""
    base_cv = (
        db.query(models.CV)
        .filter(
            models.CV.user_id == current_user.id,
            models.CV.is_base_cv.is_(True),
        )
        .first()
    )
    if not base_cv:
        raise HTTPException(status_code=404, detail="Base CV not found")
    db.delete(base_cv)
    db.commit()
    return Response(status_code=204)


@router.post("/base")
def save_base_cv(
    payload: BaseCVUpsertPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Save or update the user's Base CV parsed JSON data.
    Optionally also stores the original PDF (base64) for later viewing.
    """
    base_cv = db.query(models.CV).filter(
        models.CV.user_id == current_user.id,
        models.CV.is_base_cv == True
    ).first()

    if base_cv:
        base_cv.parsed_data = payload.parsed_data
        if payload.pdf_base64 is not None:
            base_cv.original_pdf_b64 = payload.pdf_base64 or None
        db.commit()
        db.refresh(base_cv)
    else:
        base_cv = models.CV(
            user_id=current_user.id,
            is_base_cv=True,
            parsed_data=payload.parsed_data,
            original_pdf_b64=payload.pdf_base64 or None,
        )
        db.add(base_cv)
        db.commit()
        db.refresh(base_cv)

    return {"status": "success", "message": "Base CV updated successfully"}

@router.get("/{cv_id}")
def get_cv_by_id(
    cv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve a specific CV's parsed JSON data.
    """
    cv = db.query(models.CV).filter(
        models.CV.id == cv_id,
        models.CV.user_id == current_user.id
    ).first()

    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")

    return {
        "parsed_data": cv.parsed_data,
        "latex_content": cv.latex_content
    }

