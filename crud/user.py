from sqlalchemy.orm import Session
import models
import schemas.user as schemas
from utils.auth import get_password_hash

def get_user_by_email(db: Session, email: str):
    """Find a user by their email address."""
    return db.query(models.User).filter(models.User.email == email).first()

def get_user(db: Session, user_id: int):
    """Find a user by their ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    """Create a new user with a hashed password."""
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        full_name=user.full_name,
        university=user.university,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
