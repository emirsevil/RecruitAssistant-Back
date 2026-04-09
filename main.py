from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command
import os

import models
from database import engine
from routers import quiz
from routers.workspace import router as workspace_router
from routers.cover_letter import router as cover_letter_router
from routers.generation import router as generation_router
from routers.interview import router as interview_router
from routers.voice_interview import router as voice_interview_router

# Run database migrations on startup so schema is always up-to-date.
# This handles both new databases (creates all tables) and existing ones
# (applies any pending column/table changes via Alembic migrations).
# command.upgrade(_alembic_cfg, "head")

app = FastAPI(
    title="RecruitAssistant API",
    description="AI-powered recruitment platform with CV & Cover Letter generation",
    version="1.0.0",
)

@app.on_event("startup")
def startup_event():
    # 1. Ensure DB Schema is up-to-date
    from migrate_db import run_migration
    print("Running database migrations...")
    run_migration()
    
    # 2. Ensure Default User exists
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
                university="RecruitAssistant University"
            )
            db.add(new_user)
            db.commit()
            print("Default user created.")
    except Exception as e:
        print(f"Error creating default user: {e}")
    finally:
        db.close()

# CORS — allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(quiz.router)
app.include_router(workspace_router)
app.include_router(cover_letter_router)
app.include_router(generation_router)
app.include_router(interview_router)
app.include_router(voice_interview_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}