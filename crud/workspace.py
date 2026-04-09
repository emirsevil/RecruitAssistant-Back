from sqlalchemy.orm import Session
from models import Workspace
from schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from typing import Optional


# ---------- CREATE ----------
def create_workspace(db: Session, workspace: WorkspaceCreate) -> Workspace:
    db_workspace = Workspace(
        user_id=workspace.user_id,
        company_name=workspace.company_name,
        job_name=workspace.job_name, # Eklendi
        emoji=workspace.emoji, # Eklendi
        color=workspace.color, # Eklendi
        job_description=workspace.job_description,
    )
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    return db_workspace


# ---------- READ (tek) ----------
def get_workspace(db: Session, workspace_id: int) -> Optional[Workspace]:
    return db.query(Workspace).filter(Workspace.id == workspace_id).first()


# ---------- READ (kullanıcıya ait tümü) ----------
def get_workspaces_by_user(db: Session, user_id: int) -> list[Workspace]:
    return (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .order_by(Workspace.created_at.desc())
        .all()
    )


# ---------- UPDATE ----------
def update_workspace(
    db: Session, workspace_id: int, updates: WorkspaceUpdate
) -> Optional[Workspace]:
    db_workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not db_workspace:
        return None

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_workspace, field, value)

    db.commit()
    db.refresh(db_workspace)
    return db_workspace


# ---------- DELETE ----------
def delete_workspace(db: Session, workspace_id: int) -> bool:
    db_workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not db_workspace:
        return False

    db.delete(db_workspace)
    db.commit()
    return True
