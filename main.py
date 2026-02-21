from fastapi import FastAPI
import models
from database import engine
from routers import quiz

# --- KRİTİK NOKTA ---
# Bu kod çalışınca SQLAlchemy gider, models.py'ye bakar
# ve veritabanında 'users' tablosu yoksa OLUŞTURUR.
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Include routers
app.include_router(quiz.router)

@app.get("/")
def read_root():
    return {"message": "Local Veritabanına Başarıyla Bağlandım!"}