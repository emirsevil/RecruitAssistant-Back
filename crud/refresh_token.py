from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
import models


def create_refresh_token(
    db: Session,
    user_id: int,
    token: str,
    expires_at: datetime,
    login_time: datetime,
) -> models.RefreshToken:
    """Persist a new refresh token in the database."""
    db_token = models.RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at,
        login_time=login_time,
        is_revoked=False,
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


def get_refresh_token(db: Session, token: str) -> Optional[models.RefreshToken]:
    """Look up a refresh token that is active (not revoked, not expired)."""
    return (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.token == token,
            models.RefreshToken.is_revoked == False,
            models.RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )


def revoke_refresh_token(db: Session, token: str) -> None:
    """Mark a single refresh token as revoked (token rotation)."""
    db_token = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token == token)
        .first()
    )
    if db_token:
        db_token.is_revoked = True
        db.commit()


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    """Revoke every active refresh token for a user (logout from all devices)."""
    db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == user_id,
        models.RefreshToken.is_revoked == False,
    ).update({"is_revoked": True})
    db.commit()


def cleanup_expired_tokens(db: Session) -> int:
    """Delete tokens that are expired or revoked. Returns rows deleted."""
    count = (
        db.query(models.RefreshToken)
        .filter(
            (models.RefreshToken.expires_at < datetime.now(timezone.utc))
            | (models.RefreshToken.is_revoked == True)
        )
        .delete()
    )
    db.commit()
    return count
