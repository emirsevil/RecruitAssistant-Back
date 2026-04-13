from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from schemas.dashboard import (
    ActivityLogResponse,
    DashboardResponse,
    DashboardStatsResponse,
    DashboardUpcomingEventResponse,
    SkillScoreResponse,
    WeeklyGoalsResponse,
)


DEFAULT_INTERVIEWS_TARGET = 5
DEFAULT_QUIZZES_TARGET = 2
DEFAULT_PRACTICE_MINUTES_TARGET = 300


def _start_of_week(now: datetime) -> datetime:
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _average(values: Iterable[int | None]) -> int:
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return 0
    return round(sum(clean_values) / len(clean_values))


def _score_trend(scores: list[int | None]) -> int:
    clean_scores = [score for score in scores if score is not None]
    if len(clean_scores) < 2:
        return 0

    recent_avg = _average(clean_scores[:5])
    previous_avg = _average(clean_scores[5:10])
    if previous_avg == 0:
        return 0
    return recent_avg - previous_avg


def _get_owned_completed_interviews(db: Session, user_id: int) -> list[models.Interview]:
    return (
        db.query(models.Interview)
        .join(models.Workspace, models.Workspace.id == models.Interview.workspace_id)
        .filter(
            models.Workspace.user_id == user_id,
            models.Interview.status == "completed",
        )
        .order_by(models.Interview.created_at.desc())
        .all()
    )


def _build_activity_from_logs(db: Session, user_id: int, limit: int) -> list[ActivityLogResponse]:
    logs = (
        db.query(models.ActivityLog)
        .filter(models.ActivityLog.user_id == user_id)
        .order_by(models.ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        ActivityLogResponse(
            id=f"log-{log.id}",
            title=log.title,
            description=log.description,
            activity_type=log.activity_type,
            created_at=log.created_at,
        )
        for log in logs
    ]


def _build_derived_activity(db: Session, user_id: int, limit: int) -> list[ActivityLogResponse]:
    activities: list[ActivityLogResponse] = []

    interviews = _get_owned_completed_interviews(db, user_id)[:limit]
    for interview in interviews:
        score_text = (
            f"Scored {interview.overall_score}%"
            if interview.overall_score is not None
            else "Completed practice session"
        )
        title_type = "HR" if interview.interview_type == "hr" else "Technical"
        activities.append(ActivityLogResponse(
            id=f"interview-{interview.id}",
            title=f"Completed {title_type} Mock Interview",
            description=score_text,
            activity_type="interview",
            created_at=interview.created_at,
        ))

    quiz_scores = (
        db.query(models.QuizScore)
        .filter(models.QuizScore.user_id == user_id)
        .order_by(models.QuizScore.completed_at.desc())
        .limit(limit)
        .all()
    )
    for score in quiz_scores:
        activities.append(ActivityLogResponse(
            id=f"quiz-score-{score.id}",
            title=f"Completed {score.quiz_title} Quiz",
            description=f"{score.correct_answers}/{score.total_questions} correct - {score.score}%",
            activity_type="quiz",
            created_at=score.completed_at,
        ))

    cvs = (
        db.query(models.CV)
        .filter(models.CV.user_id == user_id)
        .order_by(models.CV.created_at.desc())
        .limit(limit)
        .all()
    )
    for cv in cvs:
        activities.append(ActivityLogResponse(
            id=f"cv-{cv.id}",
            title="Updated CV",
            description="CV changes saved",
            activity_type="cv",
            created_at=cv.created_at,
        ))

    return sorted(activities, key=lambda item: item.created_at, reverse=True)[:limit]


def _get_skill_scores(db: Session, user_id: int) -> list[SkillScoreResponse]:
    stored_scores = (
        db.query(models.SkillScore)
        .filter(models.SkillScore.user_id == user_id)
        .order_by(models.SkillScore.score.asc(), models.SkillScore.updated_at.desc())
        .limit(4)
        .all()
    )
    if stored_scores:
        return [
            SkillScoreResponse(
                id=f"skill-{score.id}",
                skill_name=score.skill_name,
                category=score.category,
                score=score.score,
                updated_at=score.updated_at,
            )
            for score in stored_scores
        ]

    quiz_groups = (
        db.query(
            models.QuizScore.quiz_title,
            func.avg(models.QuizScore.score).label("avg_score"),
            func.max(models.QuizScore.completed_at).label("updated_at"),
        )
        .filter(models.QuizScore.user_id == user_id)
        .group_by(models.QuizScore.quiz_title)
        .order_by(func.avg(models.QuizScore.score).asc())
        .limit(4)
        .all()
    )

    return [
        SkillScoreResponse(
            id=f"quiz-skill-{index}",
            skill_name=quiz_title,
            category="quiz",
            score=round(avg_score or 0),
            updated_at=updated_at,
        )
        for index, (quiz_title, avg_score, updated_at) in enumerate(quiz_groups)
    ]


def get_dashboard_data(db: Session, user_id: int) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    week_start = _start_of_week(now)
    next_week_start = week_start + timedelta(days=7)
    previous_week_start = week_start - timedelta(days=7)

    progress = (
        db.query(models.DashboardUserProgress)
        .filter(models.DashboardUserProgress.user_id == user_id)
        .first()
    )

    completed_interviews = _get_owned_completed_interviews(db, user_id)
    this_week_interviews = [
        interview
        for interview in completed_interviews
        if interview.created_at and week_start <= interview.created_at < next_week_start
    ]

    hr_scores = [
        interview.overall_score
        for interview in completed_interviews
        if interview.interview_type == "hr"
    ]
    technical_scores = [
        interview.overall_score
        for interview in completed_interviews
        if interview.interview_type != "hr"
    ]

    stats = DashboardStatsResponse(
        completed_interviews=progress.completed_interviews if progress else len(completed_interviews),
        completed_interviews_this_week=len(this_week_interviews),
        avg_hr_score=progress.avg_hr_score if progress and progress.avg_hr_score is not None else _average(hr_scores[:5]),
        avg_hr_score_trend=_score_trend(hr_scores),
        avg_technical_score=(
            progress.avg_technical_score
            if progress and progress.avg_technical_score is not None
            else _average(technical_scores[:5])
        ),
        avg_technical_score_trend=_score_trend(technical_scores),
        cv_ats_score=progress.cv_ats_score if progress else 0,
    )

    weekly_goal = (
        db.query(models.WeeklyGoal)
        .filter(
            models.WeeklyGoal.user_id == user_id,
            models.WeeklyGoal.week_start == week_start.date(),
        )
        .first()
    )

    quizzes_actual = (
        db.query(models.QuizScore)
        .filter(
            models.QuizScore.user_id == user_id,
            models.QuizScore.completed_at >= week_start,
            models.QuizScore.completed_at < next_week_start,
        )
        .count()
    )

    practice_events = (
        db.query(models.ScheduleEvent)
        .filter(
            models.ScheduleEvent.user_id == user_id,
            models.ScheduleEvent.event_type == "practice",
            models.ScheduleEvent.start_time >= week_start,
            models.ScheduleEvent.start_time < next_week_start,
        )
        .all()
    )
    practice_minutes = sum(
        max(0, round((event.end_time - event.start_time).total_seconds() / 60))
        for event in practice_events
        if event.end_time and event.start_time
    )

    weekly_goals = WeeklyGoalsResponse(
        interviews_target=weekly_goal.interviews_target if weekly_goal else DEFAULT_INTERVIEWS_TARGET,
        interviews_actual=len(this_week_interviews),
        quizzes_target=weekly_goal.quizzes_target if weekly_goal else DEFAULT_QUIZZES_TARGET,
        quizzes_actual=quizzes_actual,
        practice_minutes_target=weekly_goal.practice_minutes_target if weekly_goal else DEFAULT_PRACTICE_MINUTES_TARGET,
        practice_minutes_actual=practice_minutes,
    )

    log_activity = _build_activity_from_logs(db, user_id, limit=5)
    derived_activity = _build_derived_activity(db, user_id, limit=5)
    activity_by_id = {item.id: item for item in [*log_activity, *derived_activity]}
    activity = sorted(activity_by_id.values(), key=lambda item: item.created_at, reverse=True)[:5]

    upcoming_events = (
        db.query(models.ScheduleEvent)
        .filter(
            models.ScheduleEvent.user_id == user_id,
            models.ScheduleEvent.start_time >= now,
        )
        .order_by(models.ScheduleEvent.start_time.asc())
        .limit(3)
        .all()
    )

    return DashboardResponse(
        stats=stats,
        activity=activity,
        skill_scores=_get_skill_scores(db, user_id),
        weekly_goals=weekly_goals,
        upcoming_events=[
            DashboardUpcomingEventResponse(
                id=event.id,
                title=event.title,
                event_type=event.event_type,
                start_time=event.start_time,
                end_time=event.end_time,
            )
            for event in upcoming_events
        ],
    )
