from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────

class ShortlistStatus(str, Enum):
    shortlisted = "shortlisted"
    contacted = "contacted"
    interviewing = "interviewing"
    hired = "hired"
    rejected = "rejected"


class DifficultyLevel(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"


# ── Company Schemas ───────────────────────────────────────────────────

class CompanyBase(BaseModel):
    name: str
    website: Optional[str] = None
    description: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyResponse(CompanyBase):
    id: int
    logo_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Recruiter Schemas ─────────────────────────────────────────────────

class RecruiterCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    company: CompanyCreate  # Inline company creation on first registration


class RecruiterLogin(BaseModel):
    email: EmailStr
    password: str


class RecruiterResponse(BaseModel):
    id: int
    full_name: str
    email: str
    company: CompanyResponse
    created_at: datetime

    class Config:
        from_attributes = True


# ── Job Opening Schemas ──────────────────────────────────────────────

class JobOpeningCreate(BaseModel):
    title: str
    department: Optional[str] = None
    description: str
    required_skills: Optional[str] = None  # Comma-separated
    difficulty_level: Optional[DifficultyLevel] = None


class JobOpeningResponse(BaseModel):
    id: int
    company_id: int
    title: str
    department: Optional[str] = None
    description: str
    required_skills: Optional[str] = None
    difficulty_level: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Shortlist Schemas ────────────────────────────────────────────────

class ShortlistCreate(BaseModel):
    candidate_id: int
    notes: Optional[str] = None


class ShortlistStatusUpdate(BaseModel):
    status: ShortlistStatus
    notes: Optional[str] = None


class ShortlistResponse(BaseModel):
    id: int
    job_opening_id: int
    candidate_id: int
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Candidate Search Schemas ─────────────────────────────────────────

class CandidateSearchParams(BaseModel):
    """Query parameters for searching candidates."""
    skills: Optional[str] = Field(None, description="Comma-separated skill keywords to filter by")
    education_keyword: Optional[str] = Field(None, description="Keyword to search in education field")
    professional_title: Optional[str] = Field(None, description="Keyword to search in professional title")
    min_tech_score: Optional[int] = Field(None, ge=0, le=100, description="Minimum average technical interview score")
    min_hr_score: Optional[int] = Field(None, ge=0, le=100, description="Minimum average HR interview score")
    page: int = Field(1, ge=1, description="Page number for pagination")
    page_size: int = Field(20, ge=1, le=100, description="Number of results per page")


class SkillScoreItem(BaseModel):
    skill_name: str
    category: Optional[str] = None
    score: int

    class Config:
        from_attributes = True


class CandidateProfileResponse(BaseModel):
    """Candidate profile visible to recruiters. Sensitive fields are excluded."""
    id: int
    full_name: Optional[str] = None
    professional_title: Optional[str] = None
    education: Optional[str] = None
    skills: Optional[str] = None
    bio: Optional[str] = None
    profile_image: Optional[str] = None
    created_at: datetime
    # Aggregated performance data
    skill_scores: List[SkillScoreItem] = []
    avg_technical_score: Optional[int] = None
    avg_hr_score: Optional[int] = None
    completed_interviews: int = 0

    class Config:
        from_attributes = True


class MatchBreakdown(BaseModel):
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    skill_match_pct: float = 0.0
    score_bonus: float = 0.0


class CandidateMatchResult(BaseModel):
    """Candidate profile enriched with match data for a specific job opening."""
    candidate: CandidateProfileResponse
    match_percentage: float = Field(ge=0, le=100)
    breakdown: MatchBreakdown

    class Config:
        from_attributes = True
