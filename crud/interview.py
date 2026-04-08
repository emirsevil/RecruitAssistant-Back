from sqlalchemy.orm import Session
from models import Interview


def create_interview(
    db: Session,
    workspace_id: int,
    interview_type: str,
    transcript: str = None,
    difficulty: str = None,
    categories: str = None,
    mode: str = "text",
    status: str = "in_progress",
):
    db_interview = Interview(
        workspace_id=workspace_id,
        interview_type=interview_type,
        transcript=transcript,
        difficulty=difficulty,
        categories=categories,
        mode=mode,
        status=status,
    )
    db.add(db_interview)
    db.commit()
    db.refresh(db_interview)
    return db_interview


def get_interview(db: Session, interview_id: int):
    return db.query(Interview).filter(Interview.id == interview_id).first()


def list_interviews(db: Session, workspace_id: int = None):
    """List interviews, optionally filtered by workspace, ordered newest first."""
    query = db.query(Interview)
    if workspace_id:
        query = query.filter(Interview.workspace_id == workspace_id)
    return query.order_by(Interview.created_at.desc()).all()


def update_interview_feedback(db: Session, interview_id: int, feedback: str):
    interview = get_interview(db, interview_id)
    if interview:
        interview.feedback = feedback
        db.commit()
        db.refresh(interview)
    return interview


def update_interview(db: Session, interview_id: int, **kwargs):
    """Update any fields on an interview record."""
    interview = get_interview(db, interview_id)
    if not interview:
        return None
    for key, value in kwargs.items():
        if hasattr(interview, key) and value is not None:
            setattr(interview, key, value)
    db.commit()
    db.refresh(interview)
    return interview
