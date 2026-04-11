from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
)
from schemas import quiz as quiz_schema
from crud import quiz as quiz_crud
from services.quiz_generator import (
    generate_quizzes_from_job_description,
    extract_skills_from_job_description,
    generate_targeted_quizzes
)
from crud.workspace import (
    create_workspace,
    get_workspace,
    get_workspaces_by_user,
    update_workspace,
    delete_workspace,
)
from routers.auth import get_current_user
import models

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# POST  /workspaces/
@router.post("/", response_model=WorkspaceResponse, status_code=201)
def create_new_workspace(
    workspace: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a new workspace for the authenticated user."""
    # Ensure user_id in the creation logic matches the current user
    workspace_data = workspace.model_dump()
    workspace_data["user_id"] = current_user.id
    
    # We might need a slightly different create_workspace call if the schema allows passing user_id
    from schemas.workspace import WorkspaceCreate
    updated_workspace = WorkspaceCreate(**workspace_data)
    return create_workspace(db, updated_workspace)


# GET  /workspaces/
@router.get("/", response_model=list[WorkspaceResponse])
def read_user_workspaces(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch all workspaces belonging to the authenticated user."""
    return get_workspaces_by_user(db, current_user.id)


# GET  /workspaces/{workspace_id}
@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def read_workspace(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch a specific workspace only if it belongs to the authenticated user."""
    db_workspace = get_workspace(db, workspace_id)
    if not db_workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if db_workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    return db_workspace


# PUT  /workspaces/{workspace_id}
@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_existing_workspace(
    workspace_id: int,
    updates: WorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update a workspace only if it belongs to the authenticated user."""
    db_workspace = get_workspace(db, workspace_id)
    if not db_workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if db_workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    
    return update_workspace(db, workspace_id, updates)


# DELETE  /workspaces/{workspace_id}
@router.delete("/{workspace_id}", status_code=204)
def remove_workspace(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Delete a workspace only if it belongs to the authenticated user."""
    db_workspace = get_workspace(db, workspace_id)
    if not db_workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if db_workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    delete_workspace(db, workspace_id)
    return None

@router.post("/{workspace_id}/quizzes/generate", response_model=list[quiz_schema.QuizGroupResponse])
def generate_quizzes_for_workspace(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Generate quizzes for a workspace owned by the authenticated user."""
    # Retrieve workspace to get job description
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    job_desc = workspace.job_description or ""
    generated = generate_quizzes_from_job_description(job_desc)
    
    # Use a dictionary to group by (title, difficulty)
    grouped_data = {}
    
    for q in generated:
        title = q.get("title", "Technical Quiz")
        diff = q.get("difficulty", "Medium")
        
        quiz_data = quiz_schema.QuizCreate(
            workspace_id=workspace_id,
            title=title,
            difficulty=diff,
            question=q.get("question", ""),
            options=q.get("options", []),
            correct_answer=q.get("correct_answer", "")
        )
        created = quiz_crud.create_quiz(db, quiz=quiz_data)
        
        key = (title, diff)
        if key not in grouped_data:
            grouped_data[key] = []
        grouped_data[key].append(created)
        
    return [
        quiz_schema.QuizGroupResponse(title=title, difficulty=diff, questions=questions)
        for (title, diff), questions in grouped_data.items()
    ]
@router.post("/{workspace_id}/skills/extract", response_model=list[str])
def extract_workspace_skills(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Analyze workspace JD and extract key technical skills for an owned workspace."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    
    job_desc = workspace.job_description or ""
    if not job_desc:
        return []
    
    return extract_skills_from_job_description(job_desc)

@router.post("/{workspace_id}/quizzes/generate-targeted", response_model=list[quiz_schema.QuizGroupResponse])
def generate_targeted_workspace_quizzes(
    workspace_id: int, 
    request: quiz_schema.TargetedQuizRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Generate targeted quizzes for an owned workspace."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    
    job_desc = workspace.job_description or ""
    selections = [s.model_dump() for s in request.selections]
    
    generated = generate_targeted_quizzes(job_desc, selections)
    
    grouped_data = {}
    
    for group in generated:
        title = group.get("title", "Technical Quiz")
        diff = group.get("difficulty", "Medium")
        questions = group.get("questions", [])
        
        saved_questions = []
        for q in questions:
            quiz_data = quiz_schema.QuizCreate(
                workspace_id=workspace_id,
                title=title,
                difficulty=diff,
                question=q.get("question", ""),
                options=q.get("options", []),
                correct_answer=q.get("correct_answer", "")
            )
            created = quiz_crud.create_quiz(db, quiz=quiz_data)
            saved_questions.append(created)
            
        if saved_questions:
            key = (title, diff)
            if key not in grouped_data:
                grouped_data[key] = []
            grouped_data[key].extend(saved_questions)
    
    return [
        quiz_schema.QuizGroupResponse(title=title, difficulty=diff, questions=questions)
        for (title, diff), questions in grouped_data.items()
    ]
