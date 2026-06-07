from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


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


class WorkspaceCategoryResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class WorkspaceResponse(WorkspaceBase):
    id: int
    user_id: int
    generated_cv_id: Optional[int] = None
    created_at: datetime
    categories: List[WorkspaceCategoryResponse] = []
    simulation_stage: str = "cv_preparation"
    cv_completed: bool = False
    cover_letter_completed: bool = False
    target_interview_count: int = 3

    model_config = {"from_attributes": True}


class WorkspaceCreateResponse(WorkspaceResponse):
    """Extended response returned after workspace creation, includes AI-suggested categories."""
    suggested_categories: List[str] = []


class WorkspaceCategoriesUpdate(BaseModel):
    """Body for confirming workspace categories."""
    categories: List[str]
