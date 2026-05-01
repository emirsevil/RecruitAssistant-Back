"""Analytics router — workspace-scoped progress summary."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from crud.analytics import get_analytics_summary
from crud.workspace import get_workspace
from database import get_db
from models import User
from routers.auth import get_current_user
from schemas.analytics import AnalyticsSummaryResponse


router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def read_analytics_summary(
    workspace_id: int = Query(..., description="Workspace to scope the analytics to"),
    range: Literal["30d", "90d", "all"] = Query("30d"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a single payload powering the entire Analytics page.

    Phase 1 sections: KPIs, score timeseries, topic breakdown, quiz breakdown,
    rule-based insights. All restricted to the given workspace.
    """
    workspace = get_workspace(db, workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    return get_analytics_summary(
        db=db,
        user_id=current_user.id,
        workspace_id=workspace_id,
        range_=range,
    )
