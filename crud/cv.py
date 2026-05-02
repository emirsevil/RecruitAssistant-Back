from typing import Literal, Optional, Tuple

from sqlalchemy.orm import Session

import models


CVSource = Literal["workspace", "base"]


def resolve_user_cv(
    db: Session,
    user_id: int,
    workspace: Optional[models.Workspace],
) -> Tuple[Optional[dict], Optional[CVSource]]:
    """Return the parsed CV the AI should use, plus where it came from.

    Priority: workspace's generated CV → user's base CV → (None, None).
    Only CVs owned by `user_id` are considered.
    """
    if workspace is not None and workspace.generated_cv_id:
        cv = (
            db.query(models.CV)
            .filter(
                models.CV.id == workspace.generated_cv_id,
                models.CV.user_id == user_id,
            )
            .first()
        )
        if cv and cv.parsed_data:
            return cv.parsed_data, "workspace"

    base = (
        db.query(models.CV)
        .filter(
            models.CV.user_id == user_id,
            models.CV.is_base_cv.is_(True),
        )
        .first()
    )
    if base and base.parsed_data:
        return base.parsed_data, "base"

    return None, None
