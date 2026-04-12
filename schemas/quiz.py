from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class QuizBase(BaseModel):
    workspace_id: Optional[int] = None
    title: Optional[str] = None
    difficulty: Optional[str] = None  # Easy, Medium, Hard
    question: str
    options: List[str]

    class Config:
        from_attributes = True

class QuizCreate(QuizBase):
    correct_answer: str

class QuizUpdate(BaseModel):
    workspace_id: Optional[int] = None
    title: Optional[str] = None
    difficulty: Optional[str] = None
    question: Optional[str] = None
    options: Optional[List[str]] = None
    # correct_answer is not exposed in response, but can be updated
    correct_answer: Optional[str] = None

    class Config:
        from_attributes = True

class QuizResponse(QuizBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class QuizGroupResponse(BaseModel):
    title: str
    difficulty: str
    questions: List[QuizResponse]


# --- Quiz Submit & Score Schemas ---

class AnswerItem(BaseModel):
    """Tek bir soruya verilen cevap."""
    quiz_id: int          # Sorunun DB'deki id'si
    selected_answer: str  # Kullanıcının seçtiği şık

class QuizSubmit(BaseModel):
    """Kullanıcı quiz'i bitirince bu body ile submit eder."""
    user_id: Optional[int] = None
    workspace_id: int
    quiz_title: str       # Hangi skill/konu grubu (Örn: "Python")
    difficulty: str       # Hangi zorluk seviyesi (Örn: "Easy")
    answers: List[AnswerItem]

class QuestionResult(BaseModel):
    """Her soru için doğru/yanlış detayı."""
    quiz_id: int
    question: str
    selected_answer: str
    correct_answer: str
    is_correct: bool

class QuizSubmitResponse(BaseModel):
    """Submit sonrası dönen detaylı sonuç."""
    quiz_title: str
    score: int              # Yüzdelik (0-100)
    correct_count: int
    total_questions: int
    results: List[QuestionResult]
    score_id: int           # Kaydedilen QuizScore'un id'si

class QuizScoreResponse(BaseModel):
    """Daha önce kaydedilmiş skorları listelemek için."""
    id: int
    user_id: int
    workspace_id: int
    quiz_title: str
    difficulty: str
    score: int
    total_questions: int
    correct_answers: int
    completed_at: datetime

    class Config:
        from_attributes = True

class SkillSelection(BaseModel):
    title: str
    difficulties: List[str]

class TargetedQuizRequest(BaseModel):
    selections: List[SkillSelection]
    language: Optional[str] = "tr"
