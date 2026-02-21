from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class QuizBase(BaseModel):
    workspace_id: Optional[int] = None
    question: str
    options: List[str]

    class Config:
        from_attributes = True

class QuizCreate(QuizBase):
    correct_answer: str

class QuizUpdate(BaseModel):
    workspace_id: Optional[int] = None
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
