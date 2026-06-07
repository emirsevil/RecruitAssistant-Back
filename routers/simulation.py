from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from schemas.simulation import (
    SimulationStatus,
    StageAdvanceRequest,
    TargetInterviewUpdate,
    FeedbackCreate,
    FeedbackResponse,
    SimulationProgress,
)
from routers.auth import get_current_user
from crud.workspace import get_workspace
import models

router = APIRouter(prefix="/simulation", tags=["Simulation"])

VALID_STAGES = ("cv_preparation", "interview_cycle", "completed")


def _get_owned_workspace(
    workspace_id: int, db: Session, current_user: models.User
) -> models.Workspace:
    """Helper: fetch a workspace and verify ownership."""
    ws = get_workspace(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if ws.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    return ws


# ── Status ────────────────────────────────────────────────────────────
@router.get("/{workspace_id}/status", response_model=SimulationStatus)
def get_simulation_status(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the current simulation pipeline status for a workspace."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    total_interviews = (
        db.query(models.Interview)
        .filter(models.Interview.workspace_id == workspace_id)
        .count()
    )
    total_quizzes = (
        db.query(models.Quiz)
        .filter(models.Quiz.workspace_id == workspace_id)
        .count()
    )
    total_feedbacks = (
        db.query(models.InterviewFeedback)
        .filter(
            models.InterviewFeedback.workspace_id == workspace_id,
            models.InterviewFeedback.user_id == current_user.id,
        )
        .count()
    )

    can_access = ws.simulation_stage in ("interview_cycle", "completed")

    return SimulationStatus(
        stage=ws.simulation_stage or "cv_preparation",
        cv_completed=ws.cv_completed or False,
        cover_letter_completed=ws.cover_letter_completed or False,
        total_interviews=total_interviews,
        target_interview_count=ws.target_interview_count,
        total_quizzes=total_quizzes,
        total_feedbacks=total_feedbacks,
        can_access_interviews=can_access,
    )


# ── Complete CV stage ─────────────────────────────────────────────────
@router.post("/{workspace_id}/complete-cv", response_model=SimulationStatus)
def complete_cv_stage(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark CV preparation as complete and auto-advance to interview_cycle."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    ws.cv_completed = True
    ws.simulation_stage = "interview_cycle"
    db.commit()
    db.refresh(ws)

    return get_simulation_status(workspace_id, db, current_user)


# ── Skip CV stage ────────────────────────────────────────────────────
@router.post("/{workspace_id}/skip-cv", response_model=SimulationStatus)
def skip_cv_stage(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Skip CV preparation and go directly to interview_cycle."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    ws.simulation_stage = "interview_cycle"
    db.commit()
    db.refresh(ws)

    return get_simulation_status(workspace_id, db, current_user)


# ── Advance stage (generic) ──────────────────────────────────────────
@router.post("/{workspace_id}/advance-stage", response_model=SimulationStatus)
def advance_stage(
    workspace_id: int,
    body: StageAdvanceRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Advance the simulation to a specific stage or auto-advance."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    if body.target_stage:
        if body.target_stage not in VALID_STAGES:
            raise HTTPException(status_code=400, detail=f"Geçersiz aşama: {body.target_stage}")
        ws.simulation_stage = body.target_stage
    else:
        # Auto-advance
        if ws.simulation_stage == "cv_preparation":
            ws.simulation_stage = "interview_cycle"
        elif ws.simulation_stage == "interview_cycle":
            ws.simulation_stage = "completed"
        # "completed" stays as-is

    db.commit()
    db.refresh(ws)
    return get_simulation_status(workspace_id, db, current_user)


# ── Update Target Interview Count ───────────────────────────────────────
@router.patch("/{workspace_id}/target-interviews", response_model=SimulationStatus)
def update_target_interviews(
    workspace_id: int,
    body: TargetInterviewUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update the target number of interviews for the simulation pipeline."""
    ws = _get_owned_workspace(workspace_id, db, current_user)
    
    if body.target_interview_count < 1:
        raise HTTPException(status_code=400, detail="Hedef mülakat sayısı en az 1 olmalıdır.")
        
    ws.target_interview_count = body.target_interview_count
    db.commit()
    db.refresh(ws)
    
    return get_simulation_status(workspace_id, db, current_user)


# ── Mark CV completed (from CV Studio) ────────────────────────────────
@router.post("/{workspace_id}/mark-cv-completed", response_model=SimulationStatus)
def mark_cv_completed(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark that a CV has been generated for this workspace."""
    ws = _get_owned_workspace(workspace_id, db, current_user)
    ws.cv_completed = True
    db.commit()
    db.refresh(ws)
    return get_simulation_status(workspace_id, db, current_user)


# ── Mark Cover Letter completed ───────────────────────────────────────
@router.post("/{workspace_id}/mark-cl-completed", response_model=SimulationStatus)
def mark_cover_letter_completed(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark that a cover letter has been generated for this workspace."""
    ws = _get_owned_workspace(workspace_id, db, current_user)
    ws.cover_letter_completed = True
    db.commit()
    db.refresh(ws)
    return get_simulation_status(workspace_id, db, current_user)


# ── Submit feedback ───────────────────────────────────────────────────
@router.post("/{workspace_id}/feedback", response_model=FeedbackResponse, status_code=201)
def submit_feedback(
    workspace_id: int,
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Submit real interview feedback for a workspace."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    feedback = models.InterviewFeedback(
        workspace_id=workspace_id,
        user_id=current_user.id,
        real_interview_date=body.real_interview_date,
        real_interview_type=body.real_interview_type,
        company_questions=body.company_questions,
        app_helpful_rating=body.app_helpful_rating,
        preparation_rating=body.preparation_rating,
        what_helped_most=body.what_helped_most,
        what_to_improve=body.what_to_improve,
        additional_notes=body.additional_notes,
        interview_result=body.interview_result,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


# ── List feedbacks ────────────────────────────────────────────────────
@router.get("/{workspace_id}/feedbacks", response_model=List[FeedbackResponse])
def list_feedbacks(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List all real interview feedbacks for a workspace."""
    _get_owned_workspace(workspace_id, db, current_user)

    return (
        db.query(models.InterviewFeedback)
        .filter(
            models.InterviewFeedback.workspace_id == workspace_id,
            models.InterviewFeedback.user_id == current_user.id,
        )
        .order_by(models.InterviewFeedback.created_at.desc())
        .all()
    )


# ── Progress summary ─────────────────────────────────────────────────
@router.get("/{workspace_id}/progress", response_model=SimulationProgress)
def get_simulation_progress(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get a comprehensive simulation progress summary."""
    ws = _get_owned_workspace(workspace_id, db, current_user)

    # Count completed interviews
    completed_interviews = (
        db.query(models.Interview)
        .filter(
            models.Interview.workspace_id == workspace_id,
            models.Interview.status == "completed",
        )
        .all()
    )

    # Average interview score
    scores = [i.overall_score for i in completed_interviews if i.overall_score is not None]
    avg_interview = int(sum(scores) / len(scores)) if scores else None

    # Count quiz scores
    quiz_ids = [
        q.id
        for q in db.query(models.Quiz)
        .filter(models.Quiz.workspace_id == workspace_id)
        .all()
    ]
    quiz_scores_list = (
        db.query(models.QuizScore)
        .filter(
            models.QuizScore.user_id == current_user.id,
            models.QuizScore.quiz_id.in_(quiz_ids),
        )
        .all()
        if quiz_ids
        else []
    )
    avg_quiz = (
        int(sum(qs.score for qs in quiz_scores_list) / len(quiz_scores_list))
        if quiz_scores_list
        else None
    )

    # Feedbacks
    feedbacks = (
        db.query(models.InterviewFeedback)
        .filter(
            models.InterviewFeedback.workspace_id == workspace_id,
            models.InterviewFeedback.user_id == current_user.id,
        )
        .order_by(models.InterviewFeedback.created_at.desc())
        .all()
    )

    return SimulationProgress(
        stage=ws.simulation_stage or "cv_preparation",
        cv_completed=ws.cv_completed or False,
        cover_letter_completed=ws.cover_letter_completed or False,
        total_mock_interviews=len(completed_interviews),
        total_quizzes_taken=len(quiz_scores_list),
        total_feedbacks_given=len(feedbacks),
        avg_interview_score=avg_interview,
        avg_quiz_score=avg_quiz,
        feedbacks=feedbacks,
    )
