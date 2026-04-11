from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.cover_letter import (
    CoverLetterCreate,
    CoverLetterUpdate,
    CoverLetterResponse,
)
from crud.cover_letter import (
    create_cover_letter,
    get_cover_letter,
    get_cover_letters_by_workspace,
    update_cover_letter,
    delete_cover_letter,
)
from routers.auth import get_current_user
import models
from crud.workspace import get_workspace

router = APIRouter(prefix="/cover-letters", tags=["Cover Letters"])

# POST  /cover-letters/
@router.post("/", response_model=CoverLetterResponse, status_code=201)
def create_new_cover_letter(
    cover_letter: CoverLetterCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a new cover letter if the user owns the workspace."""
    workspace = get_workspace(db, cover_letter.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    return create_cover_letter(db, cover_letter)

# GET  /cover-letters/{cover_letter_id}
@router.get("/{cover_letter_id}", response_model=CoverLetterResponse)
def read_cover_letter(cover_letter_id: int, db: Session = Depends(get_db)):
    db_cover_letter = get_cover_letter(db, cover_letter_id)
    if not db_cover_letter:
        raise HTTPException(status_code=404, detail="Cover Letter bulunamadı")
    return db_cover_letter

# GET  /cover-letters/workspace/{workspace_id}
@router.get("/workspace/{workspace_id}", response_model=list[CoverLetterResponse])
def read_workspace_cover_letters(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch cover letters for an owned workspace."""
    workspace = get_workspace(db, workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    return get_cover_letters_by_workspace(db, workspace_id)

# PUT  /cover-letters/{cover_letter_id}
@router.put("/{cover_letter_id}", response_model=CoverLetterResponse)
def update_existing_cover_letter(
    cover_letter_id: int,
    updates: CoverLetterUpdate,
    db: Session = Depends(get_db),
):
    db_cover_letter = update_cover_letter(db, cover_letter_id, updates)
    if not db_cover_letter:
        raise HTTPException(status_code=404, detail="Cover Letter bulunamadı")
    return db_cover_letter

# DELETE  /cover-letters/{cover_letter_id}
@router.delete("/{cover_letter_id}", status_code=204)
def remove_cover_letter(cover_letter_id: int, db: Session = Depends(get_db)):
    deleted = delete_cover_letter(db, cover_letter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cover Letter bulunamadı")
