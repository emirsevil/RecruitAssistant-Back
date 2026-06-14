"""
Recruiter Portal Router — Authentication, Talent Discovery, Job Postings & Pipelines.

Uses completely isolated cookie names (recruiter_access_token / recruiter_refresh_token)
and JWT role claims to prevent session conflicts with candidate users.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import os
import logging

from database import get_db
import models
import schemas.recruiter as schemas
import crud.recruiter as crud
import crud.recruiter_refresh_token as refresh_crud
from utils.auth import (
    verify_password,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    HARD_LIMIT_HOURS,
)
from services.matching import rank_candidates_for_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recruiter", tags=["Recruiter Portal"])

# ── Isolated cookie names ─────────────────────────────────────────────
RECRUITER_COOKIE_NAME = "recruiter_access_token"
RECRUITER_REFRESH_COOKIE_NAME = "recruiter_refresh_token"
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"


# ── Cookie helpers ────────────────────────────────────────────────────

def _cookie_opts() -> dict:
    """Shared cookie options — mirrors candidate auth but uses separate names."""
    return dict(
        httponly=True,
        samesite="lax" if not IS_PRODUCTION else "none",
        secure=IS_PRODUCTION,
        path="/",
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set recruiter-specific auth cookies."""
    opts = _cookie_opts()
    response.set_cookie(
        key=RECRUITER_COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **opts,
    )
    response.set_cookie(
        key=RECRUITER_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **opts,
    )


def _clear_auth_cookies(response: Response):
    """Remove recruiter auth cookies."""
    opts = _cookie_opts()
    response.delete_cookie(key=RECRUITER_COOKIE_NAME, **opts)
    response.delete_cookie(key=RECRUITER_REFRESH_COOKIE_NAME, **opts)


# ── Current-recruiter dependency ─────────────────────────────────────

async def get_current_recruiter(
    request: Request, db: Session = Depends(get_db)
) -> models.Recruiter:
    """
    Extract and verify the recruiter from the HttpOnly cookie.
    
    Security checks:
    1. Cookie must exist with the recruiter-specific name
    2. JWT must be valid and not expired
    3. JWT must contain role=recruiter claim
    4. Email in JWT must map to a real recruiter in the DB
    """
    token = request.cookies.get(RECRUITER_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    # Verify role claim
    role = payload.get("role")
    if role != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token role",
        )

    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    recruiter = crud.get_recruiter_by_email(db, email=email)
    if recruiter is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Recruiter not found",
        )
    return recruiter


# ═══════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=schemas.RecruiterResponse)
def register(
    payload: schemas.RecruiterCreate,
    db: Session = Depends(get_db),
):
    """Create a company profile and recruiter account."""
    # Check if email is already taken
    existing = crud.get_recruiter_by_email(db, email=payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create company first
    company = crud.create_company(
        db,
        name=payload.company.name,
        website=payload.company.website,
        description=payload.company.description,
    )

    # Create recruiter linked to the company
    recruiter = crud.create_recruiter(
        db,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        company_id=company.id,
    )

    # Reload with company relationship
    recruiter = crud.get_recruiter(db, recruiter.id)
    return recruiter


@router.post("/auth/login")
def login(
    response: Response,
    credentials: schemas.RecruiterLogin,
    db: Session = Depends(get_db),
):
    """Authenticate recruiter and issue HttpOnly cookies."""
    recruiter = crud.get_recruiter_by_email(db, email=credentials.email)
    if not recruiter or not verify_password(credentials.password, recruiter.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    now = datetime.now(timezone.utc)

    # Access token with role claim
    access_token = create_access_token(
        data={"sub": recruiter.email, "role": "recruiter"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # Refresh token (DB-backed)
    raw_refresh = generate_refresh_token()
    refresh_crud.create_refresh_token(
        db=db,
        recruiter_id=recruiter.id,
        token=raw_refresh,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        login_time=now,
    )

    _set_auth_cookies(response, access_token, raw_refresh)

    return {
        "message": "Successfully logged in",
        "recruiter": {
            "id": recruiter.id,
            "email": recruiter.email,
            "full_name": recruiter.full_name,
            "company": {
                "id": recruiter.company.id,
                "name": recruiter.company.name,
            },
        },
    }


@router.post("/auth/refresh")
def refresh_tokens(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate recruiter tokens with hard session limit enforcement."""
    old_refresh = request.cookies.get(RECRUITER_REFRESH_COOKIE_NAME)
    if not old_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    db_token = refresh_crud.get_refresh_token(db, old_refresh)
    if db_token is None:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Hard limit check
    now = datetime.now(timezone.utc)
    login_time = db_token.login_time
    if login_time.tzinfo is None:
        login_time = login_time.replace(tzinfo=timezone.utc)

    if now - login_time > timedelta(hours=HARD_LIMIT_HOURS):
        refresh_crud.revoke_all_recruiter_tokens(db, db_token.recruiter_id)
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )

    # Token rotation
    refresh_crud.revoke_refresh_token(db, old_refresh)

    recruiter = crud.get_recruiter(db, recruiter_id=db_token.recruiter_id)
    if recruiter is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Recruiter not found",
        )

    access_token = create_access_token(
        data={"sub": recruiter.email, "role": "recruiter"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    new_refresh = generate_refresh_token()
    refresh_crud.create_refresh_token(
        db=db,
        recruiter_id=recruiter.id,
        token=new_refresh,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        login_time=db_token.login_time,  # Preserve original login time
    )

    _set_auth_cookies(response, access_token, new_refresh)
    return {"message": "Tokens refreshed"}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Logout: revoke all recruiter refresh tokens and clear cookies."""
    token = request.cookies.get(RECRUITER_COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("role") == "recruiter":
            email = payload.get("sub")
            if email:
                recruiter = crud.get_recruiter_by_email(db, email=email)
                if recruiter:
                    refresh_crud.revoke_all_recruiter_tokens(db, recruiter.id)

    refresh_token = request.cookies.get(RECRUITER_REFRESH_COOKIE_NAME)
    if refresh_token:
        refresh_crud.revoke_refresh_token(db, refresh_token)

    _clear_auth_cookies(response)
    return {"message": "Successfully logged out"}


@router.get("/auth/me", response_model=schemas.RecruiterResponse)
def read_me(
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """Get current authenticated recruiter details."""
    return current_recruiter


# ═══════════════════════════════════════════════════════════════════════
# TALENT DISCOVERY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

def _build_candidate_response(
    candidate: models.User,
    db: Session,
) -> schemas.CandidateProfileResponse:
    """Build a safe candidate profile response — no sensitive fields leaked."""
    # Load skill scores
    skill_scores = (
        db.query(models.SkillScore)
        .filter(models.SkillScore.user_id == candidate.id)
        .all()
    )

    # Load dashboard progress
    progress = (
        db.query(models.DashboardUserProgress)
        .filter(models.DashboardUserProgress.user_id == candidate.id)
        .first()
    )

    return schemas.CandidateProfileResponse(
        id=candidate.id,
        full_name=candidate.full_name,
        professional_title=candidate.professional_title,
        education=candidate.education,
        skills=candidate.skills,
        bio=candidate.bio,
        profile_image=candidate.profile_image,
        created_at=candidate.created_at,
        skill_scores=[
            schemas.SkillScoreItem(
                skill_name=ss.skill_name,
                category=ss.category,
                score=ss.score,
            )
            for ss in skill_scores
        ],
        avg_technical_score=progress.avg_technical_score if progress else None,
        avg_hr_score=progress.avg_hr_score if progress else None,
        completed_interviews=progress.completed_interviews if progress else 0,
    )


@router.get("/candidates")
def search_candidates(
    skills: Optional[str] = Query(None, description="Comma-separated skill keywords"),
    education_keyword: Optional[str] = Query(None),
    professional_title: Optional[str] = Query(None),
    min_tech_score: Optional[int] = Query(None, ge=0, le=100),
    min_hr_score: Optional[int] = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """
    Search candidates who have opted in to be discoverable.
    Privacy: ONLY candidates with is_searchable=True are returned.
    """
    candidates, total = crud.search_candidates(
        db=db,
        skills=skills,
        education_keyword=education_keyword,
        professional_title=professional_title,
        min_tech_score=min_tech_score,
        min_hr_score=min_hr_score,
        page=page,
        page_size=page_size,
    )

    return {
        "candidates": [_build_candidate_response(c, db) for c in candidates],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/candidates/{candidate_id}", response_model=schemas.CandidateProfileResponse)
def get_candidate_detail(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """
    Detailed view of a candidate's profile.
    Returns 404 if candidate has not opted in (is_searchable=False).
    """
    candidate = crud.get_candidate_for_recruiter(db, candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found or not discoverable",
        )

    return _build_candidate_response(candidate, db)


# ═══════════════════════════════════════════════════════════════════════
# JOB POSTING & MATCHING ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/jobs", response_model=schemas.JobOpeningResponse)
def create_job(
    payload: schemas.JobOpeningCreate,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """Create a new job opening for the recruiter's company."""
    job = crud.create_job_opening(
        db=db,
        company_id=current_recruiter.company_id,
        title=payload.title,
        description=payload.description,
        department=payload.department,
        required_skills=payload.required_skills,
        difficulty_level=payload.difficulty_level.value if payload.difficulty_level else None,
    )
    return job


@router.get("/jobs", response_model=List[schemas.JobOpeningResponse])
def list_jobs(
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """List all job openings for the recruiter's company."""
    return crud.get_job_openings_by_company(db, current_recruiter.company_id)


@router.get("/jobs/{job_id}", response_model=schemas.JobOpeningResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """Get a specific job opening (must belong to recruiter's company)."""
    job = crud.get_job_opening(db, job_id)
    if not job or job.company_id != current_recruiter.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job opening not found",
        )
    return job


@router.get("/jobs/{job_id}/matches")
def get_job_matches(
    job_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """
    Compute AI relevance matches for a job opening.
    Returns candidates sorted by match percentage (highest first).
    """
    job = crud.get_job_opening(db, job_id)
    if not job or job.company_id != current_recruiter.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job opening not found",
        )

    # Get all searchable candidates
    all_candidates, total = crud.search_candidates(db=db, page=1, page_size=1000)

    # Build progress and skill_scores lookup maps
    progress_map = {}
    skill_scores_map = {}
    candidate_ids = [c.id for c in all_candidates]

    if candidate_ids:
        # Batch-load dashboard progress
        progresses = (
            db.query(models.DashboardUserProgress)
            .filter(models.DashboardUserProgress.user_id.in_(candidate_ids))
            .all()
        )
        progress_map = {p.user_id: p for p in progresses}

        # Batch-load skill scores
        all_skill_scores = (
            db.query(models.SkillScore)
            .filter(models.SkillScore.user_id.in_(candidate_ids))
            .all()
        )
        for ss in all_skill_scores:
            skill_scores_map.setdefault(ss.user_id, []).append(ss)

    # Rank candidates
    ranked = rank_candidates_for_job(
        candidates=all_candidates,
        job=job,
        progress_map=progress_map,
        skill_scores_map=skill_scores_map,
    )

    # Paginate results
    start = (page - 1) * page_size
    end = start + page_size
    page_results = ranked[start:end]

    # Build response
    matches = []
    for candidate, match_result in page_results:
        candidate_resp = _build_candidate_response(candidate, db)
        matches.append(
            schemas.CandidateMatchResult(
                candidate=candidate_resp,
                match_percentage=match_result.match_percentage,
                breakdown=schemas.MatchBreakdown(
                    matched_skills=match_result.breakdown.matched_skills,
                    missing_skills=match_result.breakdown.missing_skills,
                    skill_match_pct=match_result.breakdown.skill_match_pct,
                    score_bonus=match_result.breakdown.score_bonus,
                ),
            )
        )

    return {
        "matches": matches,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ═══════════════════════════════════════════════════════════════════════
# SHORTLIST / PIPELINE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/jobs/{job_id}/shortlist", response_model=schemas.ShortlistResponse)
def add_to_shortlist(
    job_id: int,
    payload: schemas.ShortlistCreate,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """Add a candidate to a job opening's shortlist pipeline."""
    # Verify job belongs to recruiter's company
    job = crud.get_job_opening(db, job_id)
    if not job or job.company_id != current_recruiter.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job opening not found",
        )

    # Verify candidate exists and is searchable
    candidate = crud.get_candidate_for_recruiter(db, payload.candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found or not discoverable",
        )

    # Create shortlist entry (duplicate-safe)
    entry = crud.create_shortlist_entry(
        db=db,
        job_opening_id=job_id,
        candidate_id=payload.candidate_id,
        notes=payload.notes,
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate is already shortlisted for this job",
        )

    return entry


@router.get("/jobs/{job_id}/shortlist", response_model=List[schemas.ShortlistResponse])
def list_shortlist(
    job_id: int,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """List all shortlisted candidates for a job opening."""
    job = crud.get_job_opening(db, job_id)
    if not job or job.company_id != current_recruiter.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job opening not found",
        )

    return crud.get_shortlists_for_job(db, job_id)


@router.patch("/shortlist/{shortlist_id}/status", response_model=schemas.ShortlistResponse)
def update_shortlist_entry_status(
    shortlist_id: int,
    payload: schemas.ShortlistStatusUpdate,
    db: Session = Depends(get_db),
    current_recruiter: models.Recruiter = Depends(get_current_recruiter),
):
    """Advance a candidate's status in the pipeline."""
    # Verify the shortlist entry exists and belongs to recruiter's company
    entry = crud.get_shortlist_entry(db, shortlist_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shortlist entry not found",
        )

    job = crud.get_job_opening(db, entry.job_opening_id)
    if not job or job.company_id != current_recruiter.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this shortlist entry",
        )

    updated = crud.update_shortlist_status(
        db=db,
        shortlist_id=shortlist_id,
        new_status=payload.status.value,
        notes=payload.notes,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shortlist entry not found",
        )

    return updated
