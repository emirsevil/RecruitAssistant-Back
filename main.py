from fastapi import FastAPI
import models
from database import engine
from routers import quiz
from routers.workspace import router as workspace_router

from fastapi.middleware.cors import CORSMiddleware

# --- KRİTİK NOKTA ---
# Bu kod çalışınca SQLAlchemy gider, models.py'ye bakar
# ve veritabanında 'users' tablosu yoksa OLUŞTURUR.
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Geliştirme aşamasında her yerden gelen isteğe izin ver
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(quiz.router)
app.include_router(workspace_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}