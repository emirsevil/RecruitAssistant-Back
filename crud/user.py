from sqlalchemy.orm import Session
import models
from schemas import user as user_schema

# 1. Kullanıcıyı ID'ye göre getir (Read)
def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

# 2. Kullanıcıyı Email'e göre getir (Kayıt olurken kontrol için lazım)
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

# 3. Yeni kullanıcı oluştur ve veritabanına kaydet (Create)
def create_user(db: Session, user: user_schema.UserCreate):
    # Şemadan gelen veriyi SQLAlchemy veritabanı modeline dönüştürüyoruz
    db_user = models.User(
        full_name=user.full_name,
        email=user.email,
        university=user.university
    )
    
    db.add(db_user)      # Veriyi ekle
    db.commit()          # Değişiklikleri kalıcı olarak kaydet
    db.refresh(db_user)  # Veritabanının atadığı ID'yi almak için modeli yenile
    
    return db_user