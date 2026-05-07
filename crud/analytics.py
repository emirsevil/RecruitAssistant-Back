"""Analytics aggregations.

All builders below take a (db, user_id, workspace_id, range) tuple and return
plain dicts that map onto the Pydantic schemas in `schemas/analytics.py`.

Workspace ownership is validated by the caller (router); these functions trust
the workspace_id they're given.
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Iterable, Literal, Optional

from sqlalchemy.orm import Session

import models


Range = Literal["30d", "90d", "all"]


# ─── Helpers ──────────────────────────────────────────────────────

def resolve_range(range_: Range) -> tuple[datetime, datetime, Optional[datetime]]:
    """Return (start, end, prev_start).

    `prev_start` is None for "all" (no comparable previous period).
    For 30d/90d, the previous period is the same length immediately before `start`.
    """
    end = datetime.now(timezone.utc)
    if range_ == "30d":
        start = end - timedelta(days=30)
        return start, end, start - timedelta(days=30)
    if range_ == "90d":
        start = end - timedelta(days=90)
        return start, end, start - timedelta(days=90)
    # "all"
    return datetime(2000, 1, 1, tzinfo=timezone.utc), end, None


def _in_range(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    if dt is None:
        return False
    return start <= dt < end


def _avg(values: Iterable[float]) -> float:
    cleaned = [v for v in values if v is not None]
    return round(mean(cleaned), 1) if cleaned else 0.0


def _bucket_for(dt: datetime, range_: Range) -> str:
    """Day buckets for 30d, ISO-week buckets for 90d/all.

    Why: 30 days at week granularity = ~4 dots — almost useless as a trend.
    90+ days at day granularity = noisy and crowded. Day for short windows,
    week for long ones is the standard pattern.
    """
    if range_ == "30d":
        return dt.date().isoformat()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _bucket_unit(range_: Range) -> str:
    return "day" if range_ == "30d" else "week"


# ─── Data fetchers (workspace-scoped) ────────────────────────────

def _fetch_interviews(
    db: Session, user_id: int, workspace_id: int
) -> list[models.Interview]:
    return (
        db.query(models.Interview)
        .join(models.Workspace, models.Workspace.id == models.Interview.workspace_id)
        .filter(
            models.Workspace.user_id == user_id,
            models.Interview.workspace_id == workspace_id,
            models.Interview.status == "completed",
        )
        .order_by(models.Interview.created_at.asc())
        .all()
    )


def _fetch_quiz_scores(
    db: Session, user_id: int, workspace_id: int
) -> list[tuple[models.QuizScore, models.Quiz]]:
    rows = (
        db.query(models.QuizScore, models.Quiz)
        .join(models.Quiz, models.Quiz.id == models.QuizScore.quiz_id)
        .filter(
            models.QuizScore.user_id == user_id,
            models.Quiz.workspace_id == workspace_id,
        )
        .order_by(models.QuizScore.completed_at.asc())
        .all()
    )
    return rows


# ─── Section builders ────────────────────────────────────────────

def _kpis(
    interviews: list[models.Interview],
    quiz_rows: list[tuple[models.QuizScore, models.Quiz]],
    start: datetime,
    end: datetime,
    prev_start: Optional[datetime],
) -> dict:
    """Current-period vs previous-period counters."""
    iv_curr = [iv for iv in interviews if _in_range(iv.created_at, start, end)]
    qz_curr = [qs for (qs, _q) in quiz_rows if _in_range(qs.completed_at, start, end)]

    if prev_start is not None:
        iv_prev = [iv for iv in interviews if _in_range(iv.created_at, prev_start, start)]
        qz_prev = [qs for (qs, _q) in quiz_rows if _in_range(qs.completed_at, prev_start, start)]
    else:
        iv_prev, qz_prev = [], []

    return {
        "interviews": {
            "current": len(iv_curr),
            "prev": len(iv_prev),
        },
        "avg_interview_score": {
            "current": _avg([iv.overall_score for iv in iv_curr]),
            "prev": _avg([iv.overall_score for iv in iv_prev]),
        },
        "quizzes": {
            "current": len(qz_curr),
            "prev": len(qz_prev),
        },
        "avg_quiz_score": {
            "current": _avg([qs.score for qs in qz_curr]),
            "prev": _avg([qs.score for qs in qz_prev]),
        },
    }


def _score_timeseries(
    interviews: list[models.Interview],
    quiz_rows: list[tuple[models.QuizScore, models.Quiz]],
    start: datetime,
    end: datetime,
    range_: Range,
) -> list[dict]:
    """Bucket interview + quiz scores by day (30d) or ISO week (90d/all)."""
    hr_by_bucket: dict[str, list[int]] = defaultdict(list)
    tech_by_bucket: dict[str, list[int]] = defaultdict(list)
    quiz_by_bucket: dict[str, list[int]] = defaultdict(list)

    for iv in interviews:
        if not _in_range(iv.created_at, start, end):
            continue
        if iv.overall_score is None:
            continue
        b = _bucket_for(iv.created_at, range_)
        if iv.interview_type == "hr":
            hr_by_bucket[b].append(iv.overall_score)
        else:
            tech_by_bucket[b].append(iv.overall_score)

    for qs, _q in quiz_rows:
        if not _in_range(qs.completed_at, start, end):
            continue
        b = _bucket_for(qs.completed_at, range_)
        quiz_by_bucket[b].append(qs.score)

    all_buckets = sorted(set(hr_by_bucket) | set(tech_by_bucket) | set(quiz_by_bucket))
    return [
        {
            "bucket": b,
            "interview_hr": _avg(hr_by_bucket[b]) if hr_by_bucket.get(b) else None,
            "interview_tech": _avg(tech_by_bucket[b]) if tech_by_bucket.get(b) else None,
            "quiz": _avg(quiz_by_bucket[b]) if quiz_by_bucket.get(b) else None,
        }
        for b in all_buckets
    ]


def _topic_breakdown(
    interviews: list[models.Interview],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Flatten per-question results from interview.feedback JSON.

    For each topic, returns attempts count, mean score, and a trend value
    (mean-of-recent − mean-of-first-3) once a topic has ≥4 attempts.
    Limits to topics seen at least twice to avoid noise.
    """
    # Walk in chronological order so "first N" / "recent N" is meaningful
    by_topic: dict[str, list[int]] = defaultdict(list)

    for iv in interviews:
        if not _in_range(iv.created_at, start, end):
            continue
        if not iv.feedback:
            continue
        try:
            data = json.loads(iv.feedback)
        except (json.JSONDecodeError, TypeError):
            continue
        for r in data.get("results", []) or []:
            topic = (r.get("topic") or "").strip()
            score = r.get("score")
            if not topic or score is None:
                continue
            try:
                by_topic[topic].append(int(score))
            except (TypeError, ValueError):
                continue

    rows: list[dict] = []
    for topic, scores in by_topic.items():
        if len(scores) < 2:
            continue
        trend: Optional[float] = None
        if len(scores) >= 4:
            first = mean(scores[:3])
            recent = mean(scores[-3:])
            trend = round(recent - first, 1)
        rows.append({
            "topic": topic,
            "attempts": len(scores),
            "avg_score": round(mean(scores), 1),
            "trend": trend,
        })

    rows.sort(key=lambda r: (r["avg_score"], -r["attempts"]))
    return rows


def _difficulty_breakdown(
    interviews: list[models.Interview],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Group interviews in the window by difficulty (intern/junior/mid)."""
    by_difficulty: dict[str, list[int]] = defaultdict(list)
    for iv in interviews:
        if not _in_range(iv.created_at, start, end):
            continue
        if iv.overall_score is None:
            continue
        bucket = (iv.difficulty or "unspecified").strip().lower()
        by_difficulty[bucket].append(iv.overall_score)

    # Stable presentation order
    order = ["intern", "junior", "mid", "senior", "unspecified"]
    rows = [
        {
            "difficulty": d,
            "attempts": len(scores),
            "avg_score": round(mean(scores), 1),
        }
        for d, scores in by_difficulty.items()
    ]
    rows.sort(key=lambda r: order.index(r["difficulty"]) if r["difficulty"] in order else 99)
    return rows


def _mode_split(
    interviews: list[models.Interview],
    start: datetime,
    end: datetime,
) -> dict:
    """Voice vs text — count + avg score for each mode in the window."""
    voice_scores: list[int] = []
    text_scores: list[int] = []
    for iv in interviews:
        if not _in_range(iv.created_at, start, end):
            continue
        if iv.overall_score is None:
            continue
        if (iv.mode or "text") == "avatar":
            voice_scores.append(iv.overall_score)
        else:
            text_scores.append(iv.overall_score)
    return {
        "voice": {
            "count": len(voice_scores),
            "avg_score": round(mean(voice_scores), 1) if voice_scores else 0.0,
        },
        "text": {
            "count": len(text_scores),
            "avg_score": round(mean(text_scores), 1) if text_scores else 0.0,
        },
    }


def _quiz_breakdown(
    quiz_rows: list[tuple[models.QuizScore, models.Quiz]],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """One row per quiz title in the window."""
    grouped: dict[str, list[models.QuizScore]] = defaultdict(list)
    for qs, q in quiz_rows:
        if not _in_range(qs.completed_at, start, end):
            continue
        title = (q.title or "Untitled Quiz").strip()
        grouped[title].append(qs)

    rows: list[dict] = []
    for title, scores in grouped.items():
        scores_sorted = sorted(scores, key=lambda s: s.completed_at or datetime.min.replace(tzinfo=timezone.utc))
        latest = scores_sorted[-1]
        accuracies = [
            (qs.correct_answers / qs.total_questions * 100)
            for qs in scores_sorted
            if qs.total_questions
        ]
        rows.append({
            "title": title,
            "attempts": len(scores_sorted),
            "best": max(qs.score for qs in scores_sorted),
            "latest": latest.score,
            "accuracy": round(mean(accuracies), 1) if accuracies else 0.0,
        })

    rows.sort(key=lambda r: r["latest"], reverse=True)
    return rows


def _insights(
    kpis: dict,
    topic_breakdown: list[dict],
    range_label: str,
) -> list[dict]:
    """Two simple rule-based cards. No LLM call.

    "Strong Progress": current avg ≥ +5 vs previous, with at least one attempt now.
    "Area to Focus":   lowest-scoring topic with ≥3 attempts.
    """
    cards: list[dict] = []

    avg_now = kpis["avg_interview_score"]["current"]
    avg_prev = kpis["avg_interview_score"]["prev"]
    delta = round(avg_now - avg_prev, 1)
    if avg_now > 0 and delta >= 5:
        cards.append({
            "tone": "positive",
            "title": "Strong Progress",
            "body": (
                f"Your average interview score is up {delta} points "
                f"vs the previous {range_label}. Keep the cadence."
            ),
        })

    weak = [r for r in topic_breakdown if r["attempts"] >= 3]
    if weak:
        weakest = min(weak, key=lambda r: r["avg_score"])
        cards.append({
            "tone": "warning",
            "title": "Area to Focus",
            "body": (
                f"\"{weakest['topic']}\" is your lowest-scoring topic "
                f"({weakest['avg_score']}% across {weakest['attempts']} attempts). "
                f"Schedule a focused practice session."
            ),
        })

    if not cards:
        cards.append({
            "tone": "neutral",
            "title": "Not enough data yet",
            "body": "Complete a few more interviews and quizzes to unlock progress insights.",
        })

    return cards


# ─── Public entrypoint ───────────────────────────────────────────

def get_analytics_summary(
    db: Session,
    user_id: int,
    workspace_id: int,
    range_: Range,
) -> dict:
    start, end, prev_start = resolve_range(range_)
    interviews = _fetch_interviews(db, user_id, workspace_id)
    quiz_rows = _fetch_quiz_scores(db, user_id, workspace_id)

    kpis = _kpis(interviews, quiz_rows, start, end, prev_start)
    timeseries = _score_timeseries(interviews, quiz_rows, start, end, range_)
    topics = _topic_breakdown(interviews, start, end)
    quizzes = _quiz_breakdown(quiz_rows, start, end)
    difficulties = _difficulty_breakdown(interviews, start, end)
    mode = _mode_split(interviews, start, end)
    range_label = {"30d": "30 days", "90d": "90 days", "all": "period"}.get(range_, "period")
    insights = _insights(kpis, topics, range_label)

    return {
        "range": {"start": start, "end": end},
        "bucket_unit": _bucket_unit(range_),
        "kpis": kpis,
        "score_timeseries": timeseries,
        "topic_breakdown": topics,
        "quiz_breakdown": quizzes,
        "difficulty_breakdown": difficulties,
        "mode_split": mode,
        "insights": insights,
    }
