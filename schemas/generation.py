"""
schemas/generation.py
─────────────────────
Pydantic schemas for the AI generation endpoints.
Includes structured candidate profile and generation request/response models.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# ══════════════════════════════════════════════
#  CANDIDATE PROFILE (Structured)
# ══════════════════════════════════════════════

class ExperienceEntry(BaseModel):
    """A single work experience entry."""
    company: str = Field(..., description="Company or organization name")
    title: str = Field(..., description="Job title / role")
    start_date: str = Field(..., description="Start date, e.g. 'Jan 2023' or '2023-01'")
    end_date: Optional[str] = Field(None, description="End date, or null if current")
    location: Optional[str] = Field(None, description="City, Country")
    bullets: list[str] = Field(
        default_factory=list,
        description="Achievement / responsibility bullet points",
    )


class EducationEntry(BaseModel):
    """A single education entry."""
    institution: str
    degree: str = Field(..., description="e.g. 'B.Sc. Computer Science'")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    highlights: list[str] = Field(
        default_factory=list,
        description="Honours, thesis, relevant coursework",
    )


class ProjectEntry(BaseModel):
    """A single project entry."""
    name: str
    description: str
    date: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    url: Optional[str] = None


class CandidateProfile(BaseModel):
    """
    Structured representation of a candidate's profile.
    This is sent by the frontend and forwarded to the LLM.
    """
    full_name: str
    email: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = Field(
        None,
        description="Professional summary / objective (2-3 sentences)",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Technical and soft skills",
    )
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════
#  REQUEST / RESPONSE
# ══════════════════════════════════════════════

class GenerateCVRequest(BaseModel):
    """Request body for POST /api/generate-cv"""
    candidate_profile: CandidateProfile
    job_description: str = Field(
        ..., description="Full text of the job description / posting"
    )
    workspace_id: Optional[int] = Field(
        None,
        description="If provided, the generated CV will be linked to this workspace",
    )
    special_instructions: Optional[str] = Field(
        None,
        description="Custom instructions for AI generation",
    )
    output_language: str = Field(
        "English",
        description="Language to use for the generated CV content, e.g. English or Turkish",
    )


class GenerateCoverLetterRequest(BaseModel):
    """Request body for POST /api/generate-cover-letter"""
    candidate_profile: CandidateProfile
    job_description: str = Field(
        ..., description="Full text of the job description / posting"
    )
    workspace_id: Optional[int] = Field(
        None,
        description="If provided, the generated cover letter will be saved to this workspace",
    )
    special_instructions: Optional[str] = Field(
        None,
        description="Custom instructions for AI generation",
    )
    output_language: str = Field(
        "English",
        description="Language to use for the generated cover letter content, e.g. English or Turkish",
    )


class CompileLatexRequest(BaseModel):
    """Request body for POST /api/compile-latex"""
    latex_content: str = Field(..., description="The LaTeX string to compile and save")
    workspace_id: Optional[int] = Field(
        None,
        description="If provided, the generation will be linked/saved to this workspace",
    )
    document_type: Optional[str] = Field(
        "cv", 
        description="Must be either 'cv' or 'cover_letter' to distinguish where it is saved."
    )
    cv_data: Optional[dict] = Field(
        None,
        description="The parsed JSON data of the CV to save alongside the LaTeX"
    )


class CompileResponse(BaseModel):
    """Response after compiling LaTeX to PDF."""
    pdf_base64: Optional[str] = Field(
        None,
        description="Base64-encoded compiled PDF. Null if pdflatex compilation failed.",
    )
    cv_id: Optional[int] = Field(
        None,
        description="Database ID of the saved CV record (if workspace_id was provided)",
    )
    cover_letter_id: Optional[int] = Field(
        None,
        description="Database ID of the saved cover letter (if workspace_id was provided)",
    )
