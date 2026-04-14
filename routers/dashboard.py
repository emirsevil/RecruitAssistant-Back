from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from crud.dashboard import get_dashboard_data
from database import get_db
from models import User
from routers.auth import get_current_user
from schemas.dashboard import DashboardResponse


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardResponse)
def read_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_dashboard_data(db=db, user_id=current_user.id)
