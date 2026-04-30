from pydantic import BaseModel
from typing import List, Literal, Optional
from datetime import datetime

AvatarProvider = Literal["rpm_cartesia", "liveavatar_full"]

class MockQuestion(BaseModel):
    id: int
    question: str
    topic: str
    aiResponse: bool = False

class MockInterviewRequest(BaseModel):
    workspace_id: int
    categories: str
    difficulty: str
    interview_type: str

class MockInterviewResponse(BaseModel):
    interview_id: int
    questions: List[MockQuestion]


class LiveAvatarBootstrapRequest(BaseModel):
    workspace_id: int


class LiveAvatarBootstrapResponse(BaseModel):
    provider: AvatarProvider
    liveavatar_session_id: str
    livekit_url: str
    livekit_client_token: str
    max_session_duration: int


class LiveAvatarStopRequest(BaseModel):
    workspace_id: int
    liveavatar_session_id: str
    reason: Optional[str] = "CLIENT_ABORTED"

# --- Phase 2: Evaluation Schemas ---

class QAPair(BaseModel):
    question: str
    topic: str
    answer: str

class EvaluateRequest(BaseModel):
    interview_id: int
    difficulty: str
    qa_pairs: List[QAPair]

class EvaluationResult(BaseModel):
    question: str
    topic: str
    score: int
    feedback: str

class FullEvaluationResponse(BaseModel):
    results: List[EvaluationResult]
    overall_score: int
    overall_feedback: str

# --- Phase 3: Interview History Schemas ---

class InterviewSummary(BaseModel):
    """Lightweight schema for the interview list view."""
    id: int
    workspace_id: int
    interview_type: str
    mode: str
    avatar_provider: AvatarProvider = "rpm_cartesia"
    difficulty: Optional[str] = None
    categories: Optional[str] = None
    overall_score: Optional[int] = None
    duration_seconds: Optional[int] = None
    status: str
    created_at: datetime
    company_name: Optional[str] = None  # Joined from workspace

    model_config = {"from_attributes": True}


class InterviewDetailQA(BaseModel):
    """A single Q&A pair with its evaluation."""
    question: str
    topic: str
    answer: str
    score: Optional[int] = None
    feedback: Optional[str] = None


class InterviewDetail(BaseModel):
    """Full schema for the interview detail view."""
    id: int
    workspace_id: int
    interview_type: str
    mode: str
    avatar_provider: AvatarProvider = "rpm_cartesia"
    difficulty: Optional[str] = None
    categories: Optional[str] = None
    overall_score: Optional[int] = None
    overall_feedback: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str
    created_at: datetime
    company_name: Optional[str] = None

    # Parsed from transcript/feedback JSON
    questions: List[InterviewDetailQA] = []
    conversation_history: Optional[List[dict]] = None  # Voice mode only

    model_config = {"from_attributes": True}
