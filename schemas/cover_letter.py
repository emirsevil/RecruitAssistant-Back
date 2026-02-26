from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class CoverLetterBase(BaseModel):
    content: str


class CoverLetterCreate(CoverLetterBase):
    workspace_id: int


class CoverLetterUpdate(BaseModel):
    content: Optional[str] = None


class CoverLetterResponse(CoverLetterBase):
    id: int
    workspace_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
