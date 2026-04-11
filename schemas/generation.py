"""
schemas/generation.py
─────────────────────
Pydantic schemas for the AI generation endpoints.
Includes structured candidate profile and generation request/response models.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


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
#  CV STUDIO STRUCTURED DATA
# ══════════════════════════════════════════════

class CVStudioPersonalInfo(BaseModel):
    fullName: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""


class CVStudioEducationEntry(BaseModel):
    id: str
    school: str = ""
    degree: str = ""
    field: str = ""
    startDate: str = ""
    endDate: str = ""
    details: str = ""


class CVStudioExperienceEntry(BaseModel):
    id: str
    company: str = ""
    role: str = ""
    location: str = ""
    startDate: str = ""
    endDate: str = ""
    bullets: list[str] = Field(default_factory=list)


class CVStudioProjectEntry(BaseModel):
    id: str
    name: str = ""
    role: str = ""
    techStack: str = ""
    description: str = ""


class CVStudioLinkEntry(BaseModel):
    id: str
    label: str = ""
    url: str = ""


class CVStudioData(BaseModel):
    personal: CVStudioPersonalInfo
    summary: str = ""
    education: list[CVStudioEducationEntry] = Field(default_factory=list)
    experience: list[CVStudioExperienceEntry] = Field(default_factory=list)
    projects: list[CVStudioProjectEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    links: list[CVStudioLinkEntry] = Field(default_factory=list)


class SectionQuality(BaseModel):
    status: Literal["confident", "partial", "missing"] = "missing"
    score: int = Field(0, ge=0, le=100)
    message: str = "Not detected"


class ParseQuality(BaseModel):
    overallScore: int = Field(0, ge=0, le=100)
    overallStatus: Literal["confident", "partial", "missing"] = "missing"
    sections: dict[str, SectionQuality] = Field(default_factory=dict)


class ATSAnalysisResponse(BaseModel):
    atsScore: int
    roleMatch: int
    missingSkills: list[str] = Field(default_factory=list)
    matchedSkills: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidenceLabel: str = "Based on available CV data"
    limitedConfidence: bool = False


class ParseCVResponse(BaseModel):
    cvData: CVStudioData
    warnings: list[str] = Field(default_factory=list)
    analysis: Optional[ATSAnalysisResponse] = None
    quality: ParseQuality
    extractedTextPreview: str = ""
    extractedText: str = ""
    rawExtractedText: str = ""
    sourceName: str
    sourceType: str


class AnalyzeCVRequest(BaseModel):
    cvData: CVStudioData
    job_description: str = ""
    quality: Optional[ParseQuality] = None


class ImproveSectionRequest(BaseModel):
    section_name: str
    cvData: CVStudioData
    job_description: str = ""
    instructions: str = ""


class ImproveSectionResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    improvedText: Optional[str] = None


# ══════════════════════════════════════════════
#  REQUEST / RESPONSE
# ══════════════════════════════════════════════

class GenerateCVRequest(BaseModel):
    """Request body for POST /api/generate-cv"""
    candidate_profile: Optional[CandidateProfile] = None
    raw_cv_text: Optional[str] = Field(
        None,
        description="Raw extracted CV text used as source material in upload-and-tailor mode",
    )
    job_description: str = Field(
        ..., description="Full text of the job description / posting"
    )
    additional_instructions: Optional[str] = Field(
        None,
        description="Optional user instructions for tailoring tone, emphasis, and constraints",
    )
    workspace_id: Optional[int] = Field(
        None,
        description="If provided, the generated CV will be linked to this workspace",
    )


class GenerateCoverLetterRequest(BaseModel):
    """Request body for POST /api/generate-cover-letter"""
    candidate_profile: Optional[CandidateProfile] = None
    raw_cv_text: Optional[str] = Field(
        None,
        description="Raw extracted CV text used as source material in upload-and-tailor mode",
    )
    job_description: str = Field(
        ..., description="Full text of the job description / posting"
    )
    additional_instructions: Optional[str] = Field(
        None,
        description="Optional user instructions for tailoring tone, emphasis, and constraints",
    )
    workspace_id: Optional[int] = Field(
        None,
        description="If provided, the generated cover letter will be saved to this workspace",
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
