from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from database import engine
from routers.workspace import router as workspace_router
from routers.cover_letter import router as cover_letter_router
from routers.generation import router as generation_router

# --- KRİTİK NOKTA ---
# Bu kod çalışınca SQLAlchemy gider, models.py'ye bakar
# ve veritabanında 'users' tablosu yoksa OLUŞTURUR.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RecruitAssistant API",
    description="AI-powered recruitment platform with CV & Cover Letter generation",
    version="1.0.0",
)

# CORS — allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspace_router)
app.include_router(cover_letter_router)
app.include_router(generation_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}