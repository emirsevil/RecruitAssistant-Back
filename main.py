from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from database import engine
from routers.workspace import router as workspace_router
from routers.interview import router as interview_router
from routers.voice_interview import router as voice_interview_router

# --- KRİTİK NOKTA ---
# Bu kod çalışınca SQLAlchemy gider, models.py'ye bakar
# ve veritabanında 'users' tablosu yoksa OLUŞTURUR.
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS - Frontend'in backend'e erişmesine izin ver
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspace_router)
app.include_router(interview_router)
app.include_router(voice_interview_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}