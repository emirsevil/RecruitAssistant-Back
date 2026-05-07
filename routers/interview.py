import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from schemas.interview import (
    MockInterviewRequest, MockInterviewResponse,
    EvaluateRequest, FullEvaluationResponse,
    InterviewSummary, InterviewDetail, InterviewDetailQA,
)
from crud.workspace import get_workspace
from crud.interview import create_interview, get_interview, update_interview_feedback, list_interviews, update_interview
from utils.ai_interviewer import generate_interview_questions
from utils.ai_evaluator import evaluate_interview
from utils.ai_evaluator import evaluate_interview
from models import Interview, User
from routers.auth import get_current_user

router = APIRouter(prefix="/interviews", tags=["Interviews"])


# ─── List / Detail ────────────────────────────────────────────────

@router.get("/", response_model=list[InterviewSummary])
def get_interviews(
    workspace_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all interviews, optionally filtered by an owned workspace_id and status."""
    if workspace_id:
        workspace = get_workspace(db, workspace_id)
        if not workspace or workspace.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    interviews = list_interviews(db, user_id=current_user.id, workspace_id=workspace_id)
    if status:
        interviews = [iv for iv in interviews if (iv.status or "completed") == status]
    results = []
    for iv in interviews:
        company_name = None
        if iv.workspace:
            company_name = iv.workspace.company_name

        results.append(InterviewSummary(
            id=iv.id,
            workspace_id=iv.workspace_id,
            interview_type=iv.interview_type,
            mode=iv.mode or "text",
            avatar_provider=iv.avatar_provider or "rpm_cartesia",
            difficulty=iv.difficulty,
            categories=iv.categories,
            overall_score=iv.overall_score,
            duration_seconds=iv.duration_seconds,
            status=iv.status or "completed",
            created_at=iv.created_at,
            company_name=company_name,
        ))

    return results


@router.get("/{interview_id}", response_model=InterviewDetail)
def get_interview_detail(
    interview_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get full details of a single interview if it belongs to an owned workspace."""
    iv = get_interview(db, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
        
    if iv.workspace and iv.workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu mülakata erişim yetkiniz yok")

    company_name = None
    if iv.workspace:
        company_name = iv.workspace.company_name

    # Parse questions and evaluation from the stored JSON
    questions_list: list[InterviewDetailQA] = []
    overall_feedback = None
    conversation_history = None

    # Parse feedback JSON (contains evaluation results)
    feedback_data = {}
    if iv.feedback:
        try:
            feedback_data = json.loads(iv.feedback)
        except json.JSONDecodeError:
            pass

    # Parse transcript JSON (contains original questions)
    transcript_data = []
    if iv.transcript and iv.transcript != "[voice_session_started]":
        try:
            transcript_data = json.loads(iv.transcript)
        except json.JSONDecodeError:
            pass

    if iv.mode in ("voice", "avatar"):
        # Voice mode: feedback has {qa_pairs, conversation_history, results, overall_score, overall_feedback}
        qa_pairs = feedback_data.get("qa_pairs", [])
        eval_results = feedback_data.get("results", [])
        overall_feedback = feedback_data.get("overall_feedback")
        conversation_history = feedback_data.get("conversation_history")

        eval_by_question = {r.get("question", ""): r for r in eval_results if r.get("question")}

        for i, qa in enumerate(qa_pairs):
            q_text = qa.get("question", "")
            # Try to match by exact question text first, fallback to index
            eval_r = eval_by_question.get(q_text)
            if not eval_r and i < len(eval_results):
                eval_r = eval_results[i]
            if not eval_r:
                eval_r = {}

            questions_list.append(InterviewDetailQA(
                question=q_text,
                topic=qa.get("topic", ""),
                answer=qa.get("answer", ""),
                score=eval_r.get("score"),
                feedback=eval_r.get("feedback"),
            ))
    else:
        # Text mode: feedback now has {results, overall_score, overall_feedback, qa_pairs}
        eval_results = feedback_data.get("results", [])
        qa_pairs = feedback_data.get("qa_pairs", [])
        overall_feedback = feedback_data.get("overall_feedback")

        eval_by_question = {r.get("question", ""): r for r in eval_results if r.get("question")}
        answer_by_question = {qa.get("question", ""): qa.get("answer", "") for qa in qa_pairs if qa.get("question")}

        # Use transcript_data (original questions) as the base
        for i, q in enumerate(transcript_data):
            q_text = q.get("question", "") if isinstance(q, dict) else ""
            topic = q.get("topic", "") if isinstance(q, dict) else ""
            
            answer = answer_by_question.get(q_text)
            if answer is None and i < len(qa_pairs):
                answer = qa_pairs[i].get("answer", "")
            
            eval_r = eval_by_question.get(q_text)
            if not eval_r and i < len(eval_results):
                eval_r = eval_results[i]
            if not eval_r:
                eval_r = {}

            questions_list.append(InterviewDetailQA(
                question=q_text,
                topic=topic,
                answer=answer or "",
                score=eval_r.get("score"),
                feedback=eval_r.get("feedback"),
            ))

    return InterviewDetail(
        id=iv.id,
        workspace_id=iv.workspace_id,
        interview_type=iv.interview_type,
        mode=iv.mode or "text",
        avatar_provider=iv.avatar_provider or "rpm_cartesia",
        difficulty=iv.difficulty,
        categories=iv.categories,
        overall_score=iv.overall_score,
        overall_feedback=overall_feedback,
        duration_seconds=iv.duration_seconds,
        status=iv.status or "completed",
        created_at=iv.created_at,
        company_name=company_name,
        questions=questions_list,
        conversation_history=conversation_history,
    )


# ─── Generate & Evaluate ─────────────────────────────────────────

@router.post("/generate", response_model=MockInterviewResponse)
def generate_mock_interview(
    request: MockInterviewRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    workspace = get_workspace(db, request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    if not workspace.job_description:
        raise HTTPException(status_code=400, detail="Workspace does not have a job description")

    job_description = workspace.job_description
    categories_str = ", ".join(request.categories) if request.categories else "Genel"

    # Fetch the workspace CV or fallback to Base CV
    from models import CV
    import json
    db_cv = None
    if workspace.generated_cv_id:
        db_cv = db.query(CV).filter(CV.id == workspace.generated_cv_id).first()
    if not db_cv:
        db_cv = db.query(CV).filter(CV.user_id == current_user.id, CV.is_base_cv == True).first()
        
    cv_text = ""
    if db_cv and db_cv.parsed_data:
        cv_text = json.dumps(db_cv.parsed_data, ensure_ascii=False)

    questions = generate_interview_questions(
        job_description=job_description,
        categories=categories_str,
        difficulty=request.difficulty,
        interview_type=request.interview_type,
        cv_text=cv_text
    )

    if not questions:
        raise HTTPException(status_code=500, detail="Failed to generate questions")

    transcript = json.dumps(questions)
    interview = create_interview(
        db=db,
        workspace_id=request.workspace_id,
        interview_type=request.interview_type,
        transcript=transcript,
        difficulty=request.difficulty,
        categories=categories_str,
        mode="text",
        status="in_progress",
        avatar_provider="rpm_cartesia",
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
    qa_dicts = []
    for qa in request.qa_pairs:
        qa_dict = qa.model_dump()
        ans = str(qa_dict.get("answer", "")).strip()
        if not ans:
            qa_dict["answer"] = "(Passed / No Answer)"
        qa_dicts.append(qa_dict)

    # Single batch OpenAI call
    evaluation = evaluate_interview(
        qa_pairs=qa_dicts,
        job_description=job_description,
        difficulty=request.difficulty,
        interview_type=interview.interview_type or "technical"
    )

    if not evaluation.get("results"):
        raise HTTPException(status_code=500, detail="Evaluation failed")

    # Save full data to DB: evaluation results + user's answers (qa_pairs)
    full_feedback = {
        **evaluation,
        "qa_pairs": qa_dicts,  # Preserve user's actual answers
    }
    update_interview_feedback(
        db=db,
        interview_id=request.interview_id,
        feedback=json.dumps(full_feedback, ensure_ascii=False)
    )
    update_interview(
        db=db,
        interview_id=request.interview_id,
        overall_score=evaluation.get("overall_score", 0),
        status="completed",
    )

    return FullEvaluationResponse(
        results=evaluation["results"],
        overall_score=evaluation.get("overall_score", 0),
        overall_feedback=evaluation.get("overall_feedback", "")
    )


@router.post("/{interview_id}/discard")
def discard_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an in-progress interview as cancelled.

    Used when the user refreshes mid-interview and chooses to abandon the session
    on the Mock Interview setup screen.
    """
    iv = get_interview(db, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")

    if iv.workspace and iv.workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu mülakata erişim yetkiniz yok")

    if iv.status in ("completed", "cancelled"):
        return {"id": iv.id, "status": iv.status}

    update_interview(db=db, interview_id=interview_id, status="cancelled")
    return {"id": iv.id, "status": "cancelled"}


@router.post("/discard-in-progress")
def discard_all_in_progress(
    workspace_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark every in-progress interview in a workspace as cancelled.

    Used by the "Discard Interview" prompt on the Mock Interview setup screen
    so the user clears all stale sessions in one click — otherwise abandoned
    sessions from previous attempts pile up and the prompt keeps coming back.
    """
    workspace = get_workspace(db, workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    rows = list_interviews(db, user_id=current_user.id, workspace_id=workspace_id)
    cancelled_ids: list[int] = []
    for iv in rows:
        if (iv.status or "completed") == "in_progress":
            update_interview(db=db, interview_id=iv.id, status="cancelled")
            cancelled_ids.append(iv.id)

    return {"cancelled_ids": cancelled_ids, "count": len(cancelled_ids)}
