from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from database import get_db
import models
from routers.auth import get_current_user

router = APIRouter(prefix="/api/cv", tags=["CV Management"])

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
        return {"parsed_data": None}
        
    return {"parsed_data": base_cv.parsed_data}

@router.post("/base")
def save_base_cv(
    cv_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Save or update the user's Base CV parsed JSON data.
    """
    base_cv = db.query(models.CV).filter(
        models.CV.user_id == current_user.id,
        models.CV.is_base_cv == True
    ).first()

    if base_cv:
        base_cv.parsed_data = cv_data
        db.commit()
        db.refresh(base_cv)
    else:
        base_cv = models.CV(
            user_id=current_user.id,
            is_base_cv=True,
            parsed_data=cv_data
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

