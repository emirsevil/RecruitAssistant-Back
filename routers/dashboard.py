from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from crud.dashboard import get_dashboard_data, update_or_create_weekly_goal
from database import get_db
from models import User
from routers.auth import get_current_user
from schemas.dashboard import DashboardResponse, WeeklyGoalUpdate


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardResponse)
def read_dashboard_summary(
    workspace_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard summary. Pass `workspace_id` to scope stats/activity to a single workspace.

    Schedule (`upcoming_events`) and weekly-goal targets stay user-level regardless.
    """
    if workspace_id is not None:
        workspace = (
            db.query(models.Workspace)
            .filter(models.Workspace.id == workspace_id)
            .first()
        )
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace bulunamadı")
        if workspace.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")
    return get_dashboard_data(db=db, user_id=current_user.id, workspace_id=workspace_id)


@router.put("/goals")
def update_goals(
    goals: WeeklyGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update_or_create_weekly_goal(db=db, user_id=current_user.id, goals=goals)
    return {"status": "success", "message": "Goals updated successfully"}
