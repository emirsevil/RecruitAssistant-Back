from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class SimulationStatus(BaseModel):
    """Current simulation pipeline status for a workspace."""
    stage: str  # "cv_preparation" | "interview_cycle" | "completed"
    cv_completed: bool
    cover_letter_completed: bool
    total_interviews: int
    target_interview_count: int
    total_quizzes: int
    total_feedbacks: int
    can_access_interviews: bool

    model_config = {"from_attributes": True}


class StageAdvanceRequest(BaseModel):
    """Request to advance the simulation stage."""
    target_stage: Optional[str] = None  # If None, auto-advance to next stage


class TargetInterviewUpdate(BaseModel):
    target_interview_count: int


class FeedbackCreate(BaseModel):
    """Create a real interview feedback entry."""
    real_interview_date: Optional[datetime] = None
    real_interview_type: Optional[str] = None  # "hr", "technical", "behavioral", "case_study"
    company_questions: Optional[str] = None
    app_helpful_rating: Optional[int] = None  # 1-5
    preparation_rating: Optional[int] = None  # 1-5
    what_helped_most: Optional[str] = None
    what_to_improve: Optional[str] = None
    additional_notes: Optional[str] = None
    interview_result: Optional[str] = None  # "passed", "failed", "pending"


class FeedbackResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    real_interview_date: Optional[datetime] = None
    real_interview_type: Optional[str] = None
    company_questions: Optional[str] = None
    app_helpful_rating: Optional[int] = None
    preparation_rating: Optional[int] = None
    what_helped_most: Optional[str] = None
    what_to_improve: Optional[str] = None
    additional_notes: Optional[str] = None
    interview_result: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SimulationProgress(BaseModel):
    """Overall simulation progress summary."""
    stage: str
    cv_completed: bool
    cover_letter_completed: bool
    total_mock_interviews: int
    total_quizzes_taken: int
    total_feedbacks_given: int
    avg_interview_score: Optional[int] = None
    avg_quiz_score: Optional[int] = None
    feedbacks: List[FeedbackResponse] = []
