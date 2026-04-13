from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

# --- Question Schemas (Individual questions) ---
class QuestionBase(BaseModel):
    question: str
    options: List[str]

    class Config:
        from_attributes = True

class QuestionCreate(QuestionBase):
    quiz_id: int
    correct_answer: str

class QuestionResponse(QuestionBase):
    id: int
    quiz_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Quiz Schemas (Groups of questions) ---
class QuizBase(BaseModel):
    workspace_id: Optional[int] = None
    title: str
    difficulty: str  # Easy, Medium, Hard

    class Config:
        from_attributes = True

class QuizCreate(QuizBase):
    pass

class QuizResponse(QuizBase):
    id: int
    created_at: datetime
    questions: List[QuestionResponse] = []

    class Config:
        from_attributes = True

class QuizGroupResponse(BaseModel):
    """Used for UI to show a quiz and its questions together."""
    id: int
    title: str
    difficulty: str
    questions: List[QuestionResponse]
    attempts_count: int = 0  # Number of attempts already made by the user

# --- Quiz Submit & Score Schemas ---

class AnswerItem(BaseModel):
    """Answer for a single question."""
    question_id: int      # Question's DB id
    selected_answer: str  # Chosen option

class QuizSubmit(BaseModel):
    """Body sent when a user finishes a quiz."""
    quiz_id: int          # The specific quiz set ID
    answers: List[AnswerItem]

class QuestionResult(BaseModel):
    """Result detail for each question."""
    question_id: int
    question: str
    selected_answer: str
    correct_answer: str
    is_correct: bool

class QuizSubmitResponse(BaseModel):
    """Detailed result returned after submission."""
    quiz_id: int
    score: int              # Percentage (0-100)
    correct_count: int
    total_questions: int
    results: List[QuestionResult]
    score_id: int           # Saved QuizScore entry ID
    attempt_number: int     # 1, 2, or 3

class QuizScoreResponse(BaseModel):
    """For listing past results."""
    id: int
    user_id: int
    quiz_id: int
    quiz_title: str # Calculated from relation
    difficulty: str # Calculated from relation
    score: int
    total_questions: int
    correct_answers: int
    attempt_number: int
    completed_at: datetime

    class Config:
        from_attributes = True

# --- Selection & Request Schemas ---

class SkillSelection(BaseModel):
    title: str
    difficulties: List[str]

class TargetedQuizRequest(BaseModel):
    selections: List[SkillSelection]
    language: Optional[str] = "tr"
