from pydantic import BaseModel
from typing import List, Optional

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
