from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
)
from crud.workspace import (
    create_workspace,
    get_workspace,
    get_workspaces_by_user,
    update_workspace,
    delete_workspace,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# POST  /workspaces/
@router.post("/", response_model=WorkspaceResponse, status_code=201)
def create_new_workspace(
    workspace: WorkspaceCreate,
    db: Session = Depends(get_db),
):
    return create_workspace(db, workspace)


# GET  /workspaces/{workspace_id}
@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def read_workspace(workspace_id: int, db: Session = Depends(get_db)):
    db_workspace = get_workspace(db, workspace_id)
    if not db_workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    return db_workspace


# GET  /workspaces/user/{user_id}
@router.get("/user/{user_id}", response_model=list[WorkspaceResponse])
def read_user_workspaces(user_id: int, db: Session = Depends(get_db)):
    return get_workspaces_by_user(db, user_id)


# PUT  /workspaces/{workspace_id}
@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_existing_workspace(
    workspace_id: int,
    updates: WorkspaceUpdate,
    db: Session = Depends(get_db),
):
    db_workspace = update_workspace(db, workspace_id, updates)
    if not db_workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    return db_workspace


# DELETE  /workspaces/{workspace_id}
@router.delete("/{workspace_id}", status_code=204)
def remove_workspace(workspace_id: int, db: Session = Depends(get_db)):
    deleted = delete_workspace(db, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
