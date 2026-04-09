from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class WorkspaceBase(BaseModel):
    company_name: str
    job_name: Optional[str] = None # Eklendi
    emoji: Optional[str] = None # Eklendi
    color: Optional[str] = None # Eklendi
    job_description: Optional[str] = None


class WorkspaceCreate(WorkspaceBase):
    user_id: int


class WorkspaceUpdate(BaseModel):
    company_name: Optional[str] = None
    job_description: Optional[str] = None
    generated_cv_id: Optional[int] = None


class WorkspaceResponse(WorkspaceBase):
    id: int
    user_id: int
    generated_cv_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}
