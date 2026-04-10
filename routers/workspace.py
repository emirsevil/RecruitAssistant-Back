from fastapi import APIRouter, Depends, HTTPException
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
    return None

@router.post("/{workspace_id}/quizzes/generate", response_model=list[quiz_schema.QuizGroupResponse])
def generate_quizzes_for_workspace(workspace_id: int, db: Session = Depends(get_db)):
    # Retrieve workspace to get job description
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
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
@router.get("/{workspace_id}/quizzes", response_model=list[quiz_schema.QuizGroupResponse])
def get_workspace_quizzes(workspace_id: int, db: Session = Depends(get_db)):
    """Workspace'e ait mevcut quizleri başlıklarına göre gruplayarak getir."""
    quizzes = quiz_crud.list_quizzes(db, workspace_id=workspace_id)
    
    grouped_data = {}
    for q in quizzes:
        title = q.title or "Technical Quiz"
        diff = q.difficulty or "Medium"
        key = (title, diff)
        if key not in grouped_data:
            grouped_data[key] = []
        grouped_data[key].append(q)
        
    return [
        quiz_schema.QuizGroupResponse(title=title, difficulty=diff, questions=questions)
        for (title, diff), questions in grouped_data.items()
    ]

@router.post("/{workspace_id}/skills/extract", response_model=list[str])
def extract_workspace_skills(workspace_id: int, db: Session = Depends(get_db)):
    """Analyze workspace JD and extract key technical skills."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    
    job_desc = workspace.job_description or ""
    if not job_desc:
        return []
    
    return extract_skills_from_job_description(job_desc)

@router.post("/{workspace_id}/quizzes/generate-targeted", response_model=list[quiz_schema.QuizGroupResponse])
def generate_targeted_workspace_quizzes(
    workspace_id: int, 
    request: quiz_schema.TargetedQuizRequest,
    db: Session = Depends(get_db)
):
    """Generate quizzes for specific skills and difficulties selected by the user."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    
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
