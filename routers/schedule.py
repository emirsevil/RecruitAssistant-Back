from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from crud.schedule import create_event, delete_event, get_event_for_user, list_events_for_user
from database import get_db
from models import User
from routers.auth import get_current_user
from schemas.schedule import ScheduleEventCreate, ScheduleEventResponse


router = APIRouter(prefix="/schedule", tags=["Schedule"])


@router.get("/events", response_model=list[ScheduleEventResponse])
def get_schedule_events(
    start: datetime = Query(..., description="Inclusive start of the requested range"),
    end: datetime = Query(..., description="Exclusive end of the requested range"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range end must be after range start",
        )

    return list_events_for_user(db=db, user_id=current_user.id, start=start, end=end)


@router.post("/events", response_model=ScheduleEventResponse, status_code=status.HTTP_201_CREATED)
def create_schedule_event(
    event: ScheduleEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if event.end_time <= event.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event end time must be after start time",
        )

    return create_event(db=db, user_id=current_user.id, event=event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_event = get_event_for_user(db=db, event_id=event_id, user_id=current_user.id)
    if not db_event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    delete_event(db=db, event=db_event)
    return None
