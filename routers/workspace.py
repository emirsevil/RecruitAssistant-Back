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
async def generate_quizzes_for_workspace(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Generate quizzes for a workspace owned by the authenticated user."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    job_desc = workspace.job_description or ""
    generated = await generate_quizzes_from_job_description(job_desc)
    
    quiz_groups = []
    
    # Process each generated group (title, difficulty, questions)
    for g in generated:
        title = g.get("title", "Technical Quiz")
        diff = g.get("difficulty", "Medium")
        questions_raw = g.get("questions", [])
        
        # 1. Create the Quiz Group Header
        new_quiz = quiz_crud.create_quiz(db, quiz=quiz_schema.QuizBase(
            workspace_id=workspace_id,
            title=title,
            difficulty=diff
        ))
        
        # 2. Add Questions to this specific Quiz ID
        saved_questions = []
        for q_raw in questions_raw:
            q_data = quiz_schema.QuestionCreate(
                quiz_id=new_quiz.id,
                question=q_raw.get("question", ""),
                options=q_raw.get("options", []),
                correct_answer=q_raw.get("correct_answer", "")
            )
            saved_questions.append(quiz_crud.create_question(db, question=q_data))
            
        quiz_groups.append(quiz_schema.QuizGroupResponse(
            id=new_quiz.id,
            title=title,
            difficulty=diff,
            questions=saved_questions,
            attempts_count=0
        ))
        
    return quiz_groups


@router.get("/{workspace_id}/quizzes", response_model=list[quiz_schema.QuizGroupResponse])
def list_workspace_quizzes(
    workspace_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch all quizzes for a workspace owned by the authenticated user."""
    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
        
    db_quizzes = quiz_crud.list_quizzes(db=db, workspace_id=workspace_id)
    
    response_data = []
    for q in db_quizzes:
        attempts = quiz_crud.count_quiz_attempts(db, q.id, current_user.id)
        response_data.append(quiz_schema.QuizGroupResponse(
            id=q.id,
            title=q.title,
            difficulty=q.difficulty,
            questions=q.questions, # Relationship will pull these
            attempts_count=attempts
        ))
        
    return response_data


@router.post("/{workspace_id}/skills/extract", response_model=list[str])
async def extract_workspace_skills(
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
    
    return await extract_skills_from_job_description(job_desc)

@router.post("/{workspace_id}/quizzes/generate-targeted", response_model=list[quiz_schema.QuizGroupResponse])
async def generate_targeted_workspace_quizzes(
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
    
    generated = await generate_targeted_quizzes(job_desc, selections, language=request.language or "tr")
    
    quiz_groups = []
    
    for group_data in generated:
        title = group_data.get("title", "Technical Quiz")
        diff = group_data.get("difficulty", "Medium")
        questions_raw = group_data.get("questions", [])
        
        # 1. Create the Quiz Group Header
        new_quiz = quiz_crud.create_quiz(db, quiz=quiz_schema.QuizBase(
            workspace_id=workspace_id,
            title=title,
            difficulty=diff
        ))
        
        saved_questions = []
        for q_raw in questions_raw:
            q_data = quiz_schema.QuestionCreate(
                quiz_id=new_quiz.id,
                question=q_raw.get("question", ""),
                options=q_raw.get("options", []),
                correct_answer=q_raw.get("correct_answer", "")
            )
            saved_questions.append(quiz_crud.create_question(db, question=q_data))
            
        if saved_questions:
            quiz_groups.append(quiz_schema.QuizGroupResponse(
                id=new_quiz.id,
                title=title,
                difficulty=diff,
                questions=saved_questions,
                attempts_count=0
            ))
    
    return quiz_groups
