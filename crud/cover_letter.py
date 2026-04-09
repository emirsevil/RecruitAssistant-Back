from sqlalchemy.orm import Session
from models import CoverLetter
from schemas.cover_letter import CoverLetterCreate, CoverLetterUpdate
from typing import Optional

# ---------- CREATE ----------
def create_cover_letter(db: Session, cover_letter: CoverLetterCreate) -> CoverLetter:
    db_cover_letter = CoverLetter(
        workspace_id=cover_letter.workspace_id,
        content=cover_letter.content,
    )
    db.add(db_cover_letter)
    db.commit()
    db.refresh(db_cover_letter)
    return db_cover_letter

# ---------- READ (tek) ----------
def get_cover_letter(db: Session, cover_letter_id: int) -> Optional[CoverLetter]:
    return db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id).first()

# ---------- READ (workspace'e ait tümü) ----------
def get_cover_letters_by_workspace(db: Session, workspace_id: int) -> list[CoverLetter]:
    return (
        db.query(CoverLetter)
        .filter(CoverLetter.workspace_id == workspace_id)
        .order_by(CoverLetter.created_at.desc())
        .all()
    )

# ---------- UPDATE ----------
def update_cover_letter(
    db: Session, cover_letter_id: int, updates: CoverLetterUpdate
) -> Optional[CoverLetter]:
    db_cover_letter = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id).first()
    if not db_cover_letter:
        return None

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_cover_letter, field, value)

    db.commit()
    db.refresh(db_cover_letter)
    return db_cover_letter

# ---------- DELETE ----------
def delete_cover_letter(db: Session, cover_letter_id: int) -> bool:
    db_cover_letter = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id).first()
    if not db_cover_letter:
        return False

    db.delete(db_cover_letter)
    db.commit()
    return True
