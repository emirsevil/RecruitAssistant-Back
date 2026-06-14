"""
Refresh token CRUD operations for Recruiter sessions.

Mirrors the structure of crud/refresh_token.py but operates on the
RecruiterRefreshToken model to maintain complete session isolation
between candidates and recruiters.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
import models


def create_refresh_token(
    db: Session,
    recruiter_id: int,
    token: str,
    expires_at: datetime,
    login_time: datetime,
) -> models.RecruiterRefreshToken:
    """Persist a new recruiter refresh token in the database."""
    db_token = models.RecruiterRefreshToken(
        recruiter_id=recruiter_id,
        token=token,
        expires_at=expires_at,
        login_time=login_time,
        is_revoked=False,
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


def get_refresh_token(db: Session, token: str) -> Optional[models.RecruiterRefreshToken]:
    """Look up a recruiter refresh token that is active (not revoked, not expired)."""
    return (
        db.query(models.RecruiterRefreshToken)
        .filter(
            models.RecruiterRefreshToken.token == token,
            models.RecruiterRefreshToken.is_revoked == False,
            models.RecruiterRefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )


def revoke_refresh_token(db: Session, token: str) -> None:
    """Mark a single recruiter refresh token as revoked (token rotation)."""
    db_token = (
        db.query(models.RecruiterRefreshToken)
        .filter(models.RecruiterRefreshToken.token == token)
        .first()
    )
    if db_token:
        db_token.is_revoked = True
        db.commit()


def revoke_all_recruiter_tokens(db: Session, recruiter_id: int) -> None:
    """Revoke every active refresh token for a recruiter (logout from all devices)."""
    db.query(models.RecruiterRefreshToken).filter(
        models.RecruiterRefreshToken.recruiter_id == recruiter_id,
        models.RecruiterRefreshToken.is_revoked == False,
    ).update({"is_revoked": True})
    db.commit()


def cleanup_expired_tokens(db: Session) -> int:
    """Delete recruiter tokens that are expired or revoked. Returns rows deleted."""
    count = (
        db.query(models.RecruiterRefreshToken)
        .filter(
            (models.RecruiterRefreshToken.expires_at < datetime.now(timezone.utc))
            | (models.RecruiterRefreshToken.is_revoked == True)
        )
        .delete()
    )
    db.commit()
    return count
