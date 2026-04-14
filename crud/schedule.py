from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from schemas.schedule import ScheduleEventCreate


def list_events_for_user(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
) -> List[models.ScheduleEvent]:
    return (
        db.query(models.ScheduleEvent)
        .filter(
            models.ScheduleEvent.user_id == user_id,
            models.ScheduleEvent.start_time < end,
            models.ScheduleEvent.end_time > start,
        )
        .order_by(models.ScheduleEvent.start_time.asc())
        .all()
    )


def create_event(
    db: Session,
    user_id: int,
    event: ScheduleEventCreate,
) -> models.ScheduleEvent:
    db_event = models.ScheduleEvent(
        user_id=user_id,
        title=event.title,
        event_type=event.event_type,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def get_event_for_user(
    db: Session,
    event_id: int,
    user_id: int,
) -> Optional[models.ScheduleEvent]:
    return (
        db.query(models.ScheduleEvent)
        .filter(
            models.ScheduleEvent.id == event_id,
            models.ScheduleEvent.user_id == user_id,
        )
        .first()
    )


def delete_event(
    db: Session,
    event: models.ScheduleEvent,
) -> None:
    db.delete(event)
    db.commit()
