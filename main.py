from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command
import os

import models
from database import engine
from routers import quiz
from routers.workspace import router as workspace_router
from routers.interview import router as interview_router
from routers.voice_interview import router as voice_interview_router

# Run database migrations on startup so schema is always up-to-date.
# This handles both new databases (creates all tables) and existing ones
# (applies any pending column/table changes via Alembic migrations).
_alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
command.upgrade(_alembic_cfg, "head")

app = FastAPI()

# CORS - Frontend'in backend'e erişmesine izin ver
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(quiz.router)
app.include_router(workspace_router)
app.include_router(interview_router)
app.include_router(voice_interview_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}