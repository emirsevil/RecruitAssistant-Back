from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command
import os
import logging

# Configure logging to show info messages in the console
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(message)s"
)

import models
from database import engine
from routers import quiz, auth, schedule, dashboard, analytics, cv
from routers.workspace import router as workspace_router
from routers.cover_letter import router as cover_letter_router
from routers.generation import router as generation_router
from routers.interview import router as interview_router
from routers.voice_interview import router as voice_interview_router
from utils.auth import get_password_hash

# Run database migrations before starting the app
from migrate_db import run_migration
run_migration()

app = FastAPI(
    title="RecruitAssistant API",
    description="AI-powered recruitment platform with CV & Cover Letter generation",
    version="1.0.0",
)

@app.on_event("startup")
def startup_event():
    # 1. Ensure Default User exists
    from database import SessionLocal
    from models import User
    db = SessionLocal()
    try:
        default_user = db.query(User).filter(User.id == 1).first()
        if not default_user:
            print("Default user not found, creating...")
            new_user = User(
                id=1,
                full_name="Default User",
                email="default@example.com",
                university="RecruitAssistant University",
                hashed_password=get_password_hash("password123")
            )
            db.add(new_user)
            db.commit()
            print("Default user created.")
        elif default_user.hashed_password is None:
            print("Default user password is null, updating...")
            default_user.hashed_password = get_password_hash("password123")
            default_user.email = "default@example.com" # Email'i de standart hale getirelim
            db.commit()
            print("Default user password updated.")
    except Exception as e:
        print(f"Error creating default user: {e}")
    finally:
        db.close()

# CORS — allow frontend to call the API with credentials (cookies)
def _get_allowed_origins() -> list[str]:
    default_origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }

    raw_values = [
        os.getenv("FRONTEND_URL", ""),
        os.getenv("FRONTEND_URLS", ""),
    ]

    for raw in raw_values:
        for origin in raw.split(","):
            cleaned = origin.strip().strip('"').strip("'")
            if cleaned:
                default_origins.add(cleaned)

    return sorted(default_origins)


ALLOWED_ORIGINS = _get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(quiz.router)
app.include_router(schedule.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(cv.router)
app.include_router(workspace_router)
app.include_router(cover_letter_router)
app.include_router(generation_router)
app.include_router(interview_router)
app.include_router(voice_interview_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}
