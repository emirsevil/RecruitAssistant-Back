from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from models import Workspace, WorkspaceCategory
from schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from typing import Optional, List


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


# ---------- CATEGORIES ----------
def set_workspace_categories(db: Session, workspace_id: int, category_names: List[str]) -> List[WorkspaceCategory]:
    """Replace all categories for a workspace with the given list."""
    # Delete existing
    db.query(WorkspaceCategory).filter(WorkspaceCategory.workspace_id == workspace_id).delete()

    # Insert new
    categories = []
    for name in category_names:
        name = name.strip()
        if not name:
            continue
        cat = WorkspaceCategory(workspace_id=workspace_id, name=name)
        db.add(cat)
        categories.append(cat)

    db.commit()
    for cat in categories:
        db.refresh(cat)
    return categories


def get_workspace_categories(db: Session, workspace_id: int) -> List[WorkspaceCategory]:
    """Get all categories for a workspace."""
    return (
        db.query(WorkspaceCategory)
        .filter(WorkspaceCategory.workspace_id == workspace_id)
        .order_by(WorkspaceCategory.id)
        .all()
    )


def search_all_categories(db: Session, query: str, limit: int = 20) -> List[str]:
    """Search distinct category names across all workspaces for autocomplete."""
    results = (
        db.query(WorkspaceCategory.name)
        .filter(WorkspaceCategory.name.ilike(f"%{query}%"))
        .group_by(WorkspaceCategory.name)
        .order_by(sa_func.count(WorkspaceCategory.id).desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in results]
