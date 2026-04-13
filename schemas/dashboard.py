from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    completed_interviews: int
    completed_interviews_this_week: int
    avg_hr_score: int
    avg_hr_score_trend: int
    avg_technical_score: int
    avg_technical_score_trend: int
    cv_ats_score: int


class ActivityLogResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    activity_type: str
    created_at: datetime


class SkillScoreResponse(BaseModel):
    id: str
    skill_name: str
    category: Optional[str] = None
    score: int
    updated_at: datetime


class WeeklyGoalsResponse(BaseModel):
    interviews_target: int
    interviews_actual: int
    quizzes_target: int
    quizzes_actual: int
    practice_minutes_target: int
    practice_minutes_actual: int


class DashboardUpcomingEventResponse(BaseModel):
    id: int
    title: str
    event_type: str
    start_time: datetime
    end_time: datetime


class DashboardResponse(BaseModel):
    stats: DashboardStatsResponse
    activity: list[ActivityLogResponse]
    skill_scores: list[SkillScoreResponse]
    weekly_goals: WeeklyGoalsResponse
    upcoming_events: list[DashboardUpcomingEventResponse]
