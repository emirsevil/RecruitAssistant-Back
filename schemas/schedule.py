from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


EventType = Literal["interview", "quiz", "practice", "other"]


class ScheduleEventBase(BaseModel):
    title: str
    event_type: EventType
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime


class ScheduleEventCreate(ScheduleEventBase):
    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title is required")
        return value


class ScheduleEventResponse(ScheduleEventBase):
    id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
