import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from schemas.interview import (
    MockInterviewRequest, MockInterviewResponse,
    EvaluateRequest, FullEvaluationResponse
)
from crud.workspace import get_workspace
from crud.interview import create_interview, get_interview, update_interview_feedback
from utils.ai_interviewer import generate_interview_questions
from utils.ai_evaluator import evaluate_interview
from models import Interview

router = APIRouter(prefix="/interviews", tags=["Interviews"])

@router.post("/generate", response_model=MockInterviewResponse)
def generate_mock_interview(request: MockInterviewRequest, db: Session = Depends(get_db)):
    workspace = get_workspace(db, request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if not workspace.job_description:
        raise HTTPException(status_code=400, detail="Workspace does not have a job description")
        
    job_description = workspace.job_description

    questions = generate_interview_questions(
        job_description=job_description,
        categories=request.categories,
        difficulty=request.difficulty,
        interview_type=request.interview_type
    )

    if not questions:
        raise HTTPException(status_code=500, detail="Failed to generate questions")

    transcript = json.dumps(questions)
    interview = create_interview(
        db=db,
        workspace_id=request.workspace_id,
        interview_type=request.interview_type,
        transcript=transcript
    )

    return MockInterviewResponse(
        interview_id=interview.id,
        questions=questions
    )

@router.post("/evaluate", response_model=FullEvaluationResponse)
def evaluate_mock_interview(request: EvaluateRequest, db: Session = Depends(get_db)):
    # Find the interview to get workspace context
    interview = db.query(Interview).filter(Interview.id == request.interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    workspace = get_workspace(db, interview.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if not workspace.job_description:
        raise HTTPException(status_code=400, detail="Workspace does not have a job description")
    
    job_description = workspace.job_description

    # Convert QAPair models to dicts for the evaluator
    qa_dicts = [qa.model_dump() for qa in request.qa_pairs]

    # Single batch OpenAI call
    evaluation = evaluate_interview(
        qa_pairs=qa_dicts,
        job_description=job_description,
        difficulty=request.difficulty
    )

    if not evaluation.get("results"):
        raise HTTPException(status_code=500, detail="Evaluation failed")

    # Save feedback to DB
    update_interview_feedback(
        db=db,
        interview_id=request.interview_id,
        feedback=json.dumps(evaluation)
    )

    return FullEvaluationResponse(
        results=evaluation["results"],
        overall_score=evaluation.get("overall_score", 0),
        overall_feedback=evaluation.get("overall_feedback", "")
    )
