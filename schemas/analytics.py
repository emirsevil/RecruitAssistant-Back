"""Pydantic schemas for the workspace-scoped Analytics endpoint.

Phase 1: KPI strip, score timeseries, topic breakdown, quiz breakdown,
plus rule-based insight cards. Practice-minutes / weekly-goal sections
are deferred to a later phase (their underlying data is user-scoped, not
workspace-scoped).
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class KpiCounter(BaseModel):
    """Current value vs previous-period value for trend arrows."""
    current: float
    prev: float


class AnalyticsKpis(BaseModel):
    interviews: KpiCounter
    avg_interview_score: KpiCounter
    quizzes: KpiCounter
    avg_quiz_score: KpiCounter


class ScoreBucket(BaseModel):
    """One bucket on the score-over-time chart.

    `bucket` is the start-of-week ISO date for week buckets, or just the day
    for tighter ranges. Any of the score fields may be null when there were
    no attempts of that type in the bucket.
    """
    bucket: str  # e.g. "2026-W12" or "2026-04-22"
    interview_hr: Optional[float] = None
    interview_tech: Optional[float] = None
    quiz: Optional[float] = None


class TopicRow(BaseModel):
    topic: str
    attempts: int
    avg_score: float
    # Delta vs the user's first 3 attempts on that topic. Positive means
    # improving; null when there aren't enough attempts to compute a trend.
    trend: Optional[float] = None


class QuizRow(BaseModel):
    title: str
    attempts: int
    best: int
    latest: int
    accuracy: float  # Mean correct/total across attempts (%)


class DifficultyRow(BaseModel):
    """Avg performance per difficulty bucket — shows whether the user is leveling up."""
    difficulty: str  # "intern" | "junior" | "mid" | other
    attempts: int
    avg_score: float


class ModeBucket(BaseModel):
    count: int
    avg_score: float


class ModeSplit(BaseModel):
    voice: ModeBucket
    text: ModeBucket


class InsightCard(BaseModel):
    tone: Literal["positive", "warning", "neutral"]
    title: str
    body: str


class AnalyticsSummaryResponse(BaseModel):
    range: TimeRange
    bucket_unit: Literal["day", "week"]
    kpis: AnalyticsKpis
    score_timeseries: list[ScoreBucket]
    topic_breakdown: list[TopicRow]
    quiz_breakdown: list[QuizRow]
    difficulty_breakdown: list[DifficultyRow]
    mode_split: ModeSplit
    insights: list[InsightCard]
