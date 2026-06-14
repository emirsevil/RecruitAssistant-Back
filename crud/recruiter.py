from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func

import models
from utils.auth import get_password_hash


# ═══════════════════════════════════════════════════════════════════════
# COMPANY CRUD
# ═══════════════════════════════════════════════════════════════════════

def create_company(db: Session, name: str, website: Optional[str] = None, description: Optional[str] = None) -> models.Company:
    """Create a new company profile."""
    company = models.Company(
        name=name,
        website=website,
        description=description,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def get_company(db: Session, company_id: int) -> Optional[models.Company]:
    """Find a company by ID."""
    return db.query(models.Company).filter(models.Company.id == company_id).first()


# ═══════════════════════════════════════════════════════════════════════
# RECRUITER CRUD
# ═══════════════════════════════════════════════════════════════════════

def create_recruiter(
    db: Session,
    full_name: str,
    email: str,
    password: str,
    company_id: int,
) -> models.Recruiter:
    """Create a new recruiter with a hashed password."""
    recruiter = models.Recruiter(
        company_id=company_id,
        full_name=full_name,
        email=email,
        hashed_password=get_password_hash(password),
    )
    db.add(recruiter)
    db.commit()
    db.refresh(recruiter)
    return recruiter


def get_recruiter_by_email(db: Session, email: str) -> Optional[models.Recruiter]:
    """Find a recruiter by email (with company eagerly loaded)."""
    return (
        db.query(models.Recruiter)
        .options(joinedload(models.Recruiter.company))
        .filter(models.Recruiter.email == email)
        .first()
    )


def get_recruiter(db: Session, recruiter_id: int) -> Optional[models.Recruiter]:
    """Find a recruiter by ID (with company eagerly loaded)."""
    return (
        db.query(models.Recruiter)
        .options(joinedload(models.Recruiter.company))
        .filter(models.Recruiter.id == recruiter_id)
        .first()
    )


# ═══════════════════════════════════════════════════════════════════════
# JOB OPENING CRUD
# ═══════════════════════════════════════════════════════════════════════

def create_job_opening(
    db: Session,
    company_id: int,
    title: str,
    description: str,
    department: Optional[str] = None,
    required_skills: Optional[str] = None,
    difficulty_level: Optional[str] = None,
) -> models.JobOpening:
    """Create a new job opening for a company."""
    job = models.JobOpening(
        company_id=company_id,
        title=title,
        description=description,
        department=department,
        required_skills=required_skills,
        difficulty_level=difficulty_level,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job_opening(db: Session, job_id: int) -> Optional[models.JobOpening]:
    """Find a job opening by ID."""
    return db.query(models.JobOpening).filter(models.JobOpening.id == job_id).first()


def get_job_openings_by_company(db: Session, company_id: int) -> List[models.JobOpening]:
    """List all job openings for a company, newest first."""
    return (
        db.query(models.JobOpening)
        .filter(models.JobOpening.company_id == company_id)
        .order_by(models.JobOpening.created_at.desc())
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════
# SHORTLIST CRUD
# ═══════════════════════════════════════════════════════════════════════

def create_shortlist_entry(
    db: Session,
    job_opening_id: int,
    candidate_id: int,
    notes: Optional[str] = None,
) -> Optional[models.Shortlist]:
    """Add a candidate to a job's shortlist. Returns None if duplicate."""
    # Check for existing entry to give a clean error instead of DB crash
    existing = (
        db.query(models.Shortlist)
        .filter(
            models.Shortlist.job_opening_id == job_opening_id,
            models.Shortlist.candidate_id == candidate_id,
        )
        .first()
    )
    if existing:
        return None  # Caller handles the 409 Conflict response

    entry = models.Shortlist(
        job_opening_id=job_opening_id,
        candidate_id=candidate_id,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_shortlist_status(
    db: Session,
    shortlist_id: int,
    new_status: str,
    notes: Optional[str] = None,
) -> Optional[models.Shortlist]:
    """Update the pipeline status of a shortlist entry."""
    entry = db.query(models.Shortlist).filter(models.Shortlist.id == shortlist_id).first()
    if not entry:
        return None
    entry.status = new_status
    if notes is not None:
        entry.notes = notes
    db.commit()
    db.refresh(entry)
    return entry


def get_shortlists_for_job(db: Session, job_opening_id: int) -> List[models.Shortlist]:
    """List all shortlisted candidates for a job opening."""
    return (
        db.query(models.Shortlist)
        .options(joinedload(models.Shortlist.candidate))
        .filter(models.Shortlist.job_opening_id == job_opening_id)
        .order_by(models.Shortlist.created_at.desc())
        .all()
    )


def get_shortlist_entry(db: Session, shortlist_id: int) -> Optional[models.Shortlist]:
    """Find a shortlist entry by ID."""
    return db.query(models.Shortlist).filter(models.Shortlist.id == shortlist_id).first()


# ═══════════════════════════════════════════════════════════════════════
# CANDIDATE SEARCH
# ═══════════════════════════════════════════════════════════════════════

def search_candidates(
    db: Session,
    skills: Optional[str] = None,
    education_keyword: Optional[str] = None,
    professional_title: Optional[str] = None,
    min_tech_score: Optional[int] = None,
    min_hr_score: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[models.User], int]:
    """
    Search candidates who have opted in (is_searchable=True).
    Returns (candidates_list, total_count).
    
    The is_searchable filter is ALWAYS applied — it cannot be bypassed.
    """
    # Base query — immutable privacy filter
    query = db.query(models.User).filter(models.User.is_searchable == True)

    # Optional filters
    if skills:
        skill_keywords = [s.strip().lower() for s in skills.split(",") if s.strip()]
        for skill in skill_keywords:
            query = query.filter(
                sql_func.lower(models.User.skills).contains(skill)
            )

    if education_keyword:
        query = query.filter(
            sql_func.lower(models.User.education).contains(education_keyword.strip().lower())
        )

    if professional_title:
        query = query.filter(
            sql_func.lower(models.User.professional_title).contains(professional_title.strip().lower())
        )

    # Score-based filters (join with dashboard_user_progress)
    if min_tech_score is not None or min_hr_score is not None:
        query = query.join(
            models.DashboardUserProgress,
            models.User.id == models.DashboardUserProgress.user_id,
        )
        if min_tech_score is not None:
            query = query.filter(
                models.DashboardUserProgress.avg_technical_score >= min_tech_score
            )
        if min_hr_score is not None:
            query = query.filter(
                models.DashboardUserProgress.avg_hr_score >= min_hr_score
            )

    # Count before pagination
    total = query.count()

    # Pagination
    offset = (page - 1) * page_size
    candidates = query.order_by(models.User.created_at.desc()).offset(offset).limit(page_size).all()

    return candidates, total


def get_candidate_for_recruiter(db: Session, candidate_id: int) -> Optional[models.User]:
    """
    Get a single candidate's full profile — ONLY if they are searchable.
    """
    return (
        db.query(models.User)
        .filter(
            models.User.id == candidate_id,
            models.User.is_searchable == True,
        )
        .first()
    )
