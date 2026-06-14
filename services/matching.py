"""
Candidate–Job matching service.

Phase 1: Rule-based matching (skill keyword intersection + score thresholds).
Structured behind a clean interface so it can be swapped with LLM-driven
matching (Phase 2+) without touching any endpoint code.
"""

from typing import List, Optional
from dataclasses import dataclass, field

import models


@dataclass
class MatchBreakdown:
    """Detailed breakdown of how a match score was computed."""
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    skill_match_pct: float = 0.0
    score_bonus: float = 0.0


@dataclass
class MatchResult:
    """Final match result for a candidate against a job opening."""
    match_percentage: float = 0.0
    breakdown: MatchBreakdown = field(default_factory=MatchBreakdown)


def _parse_skills(raw: Optional[str]) -> List[str]:
    """
    Parse a comma-separated skills string into a normalized list.
    Handles None, empty strings, and extra whitespace gracefully.
    """
    if not raw:
        return []
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def compute_match_score(
    candidate: models.User,
    job: models.JobOpening,
    dashboard_progress: Optional[models.DashboardUserProgress] = None,
    skill_scores: Optional[List[models.SkillScore]] = None,
) -> MatchResult:
    """
    Compute a match score between a candidate and a job opening.
    
    Algorithm (Phase 1 — Rule-based):
    1. Extract & normalize candidate skills from User.skills
    2. Extract & normalize required skills from JobOpening.required_skills
    3. Compute skill intersection percentage (0-100) — weight: 70%
    4. Factor in candidate's average interview scores — weight: 20%
    5. Factor in individual skill_scores for matched skills — weight: 10%
    6. Clamp final result to [0, 100]
    
    All inputs are handled defensively — None/empty values result in 0
    contribution for that component, never a crash.
    """
    breakdown = MatchBreakdown()

    # ── 1. Skill matching (70% weight) ──────────────────────────────
    candidate_skills = _parse_skills(candidate.skills)
    required_skills = _parse_skills(job.required_skills)

    if not required_skills:
        # No required skills specified → every candidate is a partial match
        skill_pct = 50.0
        breakdown.matched_skills = candidate_skills[:10]  # Show up to 10
        breakdown.missing_skills = []
    elif not candidate_skills:
        # Candidate has no skills listed → 0% skill match
        skill_pct = 0.0
        breakdown.matched_skills = []
        breakdown.missing_skills = required_skills
    else:
        candidate_skill_set = set(candidate_skills)
        required_skill_set = set(required_skills)

        matched = candidate_skill_set & required_skill_set
        missing = required_skill_set - candidate_skill_set

        breakdown.matched_skills = sorted(matched)
        breakdown.missing_skills = sorted(missing)

        skill_pct = (len(matched) / len(required_skill_set)) * 100.0

    breakdown.skill_match_pct = round(skill_pct, 1)

    # ── 2. Interview score bonus (20% weight) ──────────────────────
    score_bonus = 0.0
    if dashboard_progress:
        tech = dashboard_progress.avg_technical_score or 0
        hr = dashboard_progress.avg_hr_score or 0
        # Average of available scores, normalized to 0-100
        avg_score = 0.0
        count = 0
        if tech > 0:
            avg_score += tech
            count += 1
        if hr > 0:
            avg_score += hr
            count += 1
        if count > 0:
            avg_score = avg_score / count
        score_bonus = avg_score  # Already 0-100

    breakdown.score_bonus = round(score_bonus, 1)

    # ── 3. Skill score bonus (10% weight) ──────────────────────────
    skill_score_bonus = 0.0
    if skill_scores and breakdown.matched_skills:
        # Find skill scores for matched skills
        score_map = {ss.skill_name.lower(): ss.score for ss in skill_scores}
        matched_scores = [
            score_map[s] for s in breakdown.matched_skills if s in score_map
        ]
        if matched_scores:
            skill_score_bonus = sum(matched_scores) / len(matched_scores)

    # ── 4. Weighted combination ────────────────────────────────────
    final = (
        skill_pct * 0.70
        + score_bonus * 0.20
        + skill_score_bonus * 0.10
    )

    # Clamp to [0, 100]
    final = max(0.0, min(100.0, final))

    return MatchResult(
        match_percentage=round(final, 1),
        breakdown=breakdown,
    )


def rank_candidates_for_job(
    candidates: List[models.User],
    job: models.JobOpening,
    progress_map: dict,
    skill_scores_map: dict,
) -> List[tuple]:
    """
    Rank a list of candidates against a job opening.
    
    Args:
        candidates: List of User objects (already filtered by is_searchable)
        job: The JobOpening to match against
        progress_map: {user_id: DashboardUserProgress} lookup
        skill_scores_map: {user_id: [SkillScore, ...]} lookup
    
    Returns:
        List of (User, MatchResult) tuples sorted by match_percentage DESC
    """
    results = []
    for candidate in candidates:
        result = compute_match_score(
            candidate=candidate,
            job=job,
            dashboard_progress=progress_map.get(candidate.id),
            skill_scores=skill_scores_map.get(candidate.id, []),
        )
        results.append((candidate, result))

    # Sort by match percentage, highest first
    results.sort(key=lambda x: x[1].match_percentage, reverse=True)
    return results
