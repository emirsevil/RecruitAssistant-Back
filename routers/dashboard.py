from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from crud.dashboard import get_dashboard_data, update_or_create_weekly_goal
from database import get_db
from models import User
from routers.auth import get_current_user
from schemas.dashboard import DashboardResponse, WeeklyGoalUpdate


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardResponse)
def read_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_dashboard_data(db=db, user_id=current_user.id)


@router.put("/goals")
def update_goals(
    goals: WeeklyGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update_or_create_weekly_goal(db=db, user_id=current_user.id, goals=goals)
    return {"status": "success", "message": "Goals updated successfully"}
