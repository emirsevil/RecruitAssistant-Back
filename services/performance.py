"""
services/performance.py
───────────────────────
Aggregates a candidate's on-platform performance (completed interviews and
quizzes) into the persisted, recruiter-facing signals that the matching engine
(services/matching.py) and the talent-search score filters (crud/recruiter.py)
already read but that nothing previously wrote:

  - DashboardUserProgress.completed_interviews / avg_technical_score / avg_hr_score
  - SkillScore rows (per-skill proficiency)

The candidate's own dashboard computes the same averages live for display
(crud/dashboard.py); persisting them here is what makes that performance flow
through to recruiters.

Triggered from the two DB write-chokepoints — crud/interview.update_interview()
on completion and crud/quiz.create_quiz_score() — and from the one-off
scripts/backfill_performance.py.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import models
# Reuse the exact query + averaging the candidate dashboard uses, so the
# recruiter-facing numbers and the candidate's own dashboard always agree.
from crud.dashboard import _get_owned_completed_interviews, _average

logger = logging.getLogger(__name__)


def _parse_categories(raw: Optional[str]) -> List[str]:
    """Parse Interview.categories (a comma-separated string, e.g. 'Python, SQL')
    into a normalized lowercase token list. Defensive against None/empty."""
    if not raw:
        return []
    return [token.strip().lower() for token in str(raw).split(",") if token.strip()]


def _get_or_create_progress(db: Session, user_id: int) -> models.DashboardUserProgress:
    progress = (
        db.query(models.DashboardUserProgress)
        .filter(models.DashboardUserProgress.user_id == user_id)
        .first()
    )
    if progress is None:
        progress = models.DashboardUserProgress(user_id=user_id)
        db.add(progress)
    return progress


def recompute_candidate_performance(db: Session, user_id: int) -> None:
    """Recompute and persist all performance signals for one candidate.

    Idempotent — safe to call repeatedly and from the backfill script. Never
    raises: aggregation must not break interview/quiz completion.
    """
    try:
        interviews = _get_owned_completed_interviews(db, user_id)

        hr_scores = [
            iv.overall_score for iv in interviews
            if iv.interview_type == "hr" and iv.overall_score is not None
        ]
        technical_scores = [
            iv.overall_score for iv in interviews
            if iv.interview_type != "hr" and iv.overall_score is not None
        ]

        # ── 1. Persist headline averages (mirror dashboard's last-5 logic) ──
        progress = _get_or_create_progress(db, user_id)
        progress.completed_interviews = len(interviews)
        progress.avg_hr_score = _average(hr_scores[:5]) if hr_scores else None
        progress.avg_technical_score = (
            _average(technical_scores[:5]) if technical_scores else None
        )

        # ── 2. Derive per-skill SkillScore rows ─────────────────────────────
        # buckets: (skill_name_lower, category) -> [scores]
        buckets: Dict[Tuple[str, str], List[int]] = defaultdict(list)

        for iv in interviews:
            if iv.overall_score is None:
                continue
            category = "hr" if iv.interview_type == "hr" else "technical"
            for token in _parse_categories(iv.categories):
                buckets[(token, category)].append(iv.overall_score)

        quiz_scores = (
            db.query(models.QuizScore)
            .filter(models.QuizScore.user_id == user_id)
            .all()
        )
        for qs in quiz_scores:
            title = qs.quiz.title if qs.quiz and qs.quiz.title else None
            if not title or qs.score is None:
                continue
            buckets[(title.strip().lower(), "quiz")].append(qs.score)

        # Upsert: clear the user's existing derived rows, then re-insert the
        # per-bucket averages. Safe because nothing else writes skill_scores.
        db.query(models.SkillScore).filter(
            models.SkillScore.user_id == user_id
        ).delete(synchronize_session=False)

        for (skill_name, category), scores in buckets.items():
            db.add(models.SkillScore(
                user_id=user_id,
                skill_name=skill_name,
                category=category,
                score=round(sum(scores) / len(scores)),
            ))

        db.commit()
    except Exception as exc:  # never break the completion flow
        db.rollback()
        logger.warning(
            "Failed to recompute performance for user_id=%s: %s", user_id, exc
        )
