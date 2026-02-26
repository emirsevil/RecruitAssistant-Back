from fastapi import FastAPI
import models
from database import engine
from routers.workspace import router as workspace_router
from routers.cover_letter import router as cover_letter_router

# --- KRİTİK NOKTA ---
# Bu kod çalışınca SQLAlchemy gider, models.py'ye bakar
# ve veritabanında 'users' tablosu yoksa OLUŞTURUR.
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(workspace_router)
app.include_router(cover_letter_router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}