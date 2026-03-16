from sqlalchemy.orm import Session
from models import Interview

def create_interview(db: Session, workspace_id: int, interview_type: str, transcript: str = None):
    db_interview = Interview(
        workspace_id=workspace_id,
        interview_type=interview_type,
        transcript=transcript
    )
    db.add(db_interview)
    db.commit()
    db.refresh(db_interview)
    return db_interview

def get_interview(db: Session, interview_id: int):
    return db.query(Interview).filter(Interview.id == interview_id).first()

def update_interview_feedback(db: Session, interview_id: int, feedback: str):
    interview = get_interview(db, interview_id)
    if interview:
        interview.feedback = feedback
        db.commit()
        db.refresh(interview)
    return interview
