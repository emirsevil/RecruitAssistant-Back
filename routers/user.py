from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import crud.user as crud
import schemas.user as schemas

# Router'ı tanımlıyoruz. prefix="/users" diyerek tüm linklerin başına /users eklemiş oluyoruz.
router = APIRouter(
    prefix="/users",
    tags=["Users"] # Swagger UI'da başlık olarak düzgün görünmesi için
)

# Veritabanı Bağlantısı (Dependency)
# Her API isteğinde veritabanı kapısını açar, işlem bitince güvenle kapatır.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 1. Yeni Kullanıcı Oluşturma (Kayıt Ol)
@router.post("/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Önce bakıyoruz: Bu email ile kayıtlı biri var mı?
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        # Varsa, 400 Bad Request hatası fırlatıyoruz
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kullanımda.")
    
    # Yoksa, crud dosyasındaki fonksiyonumuzu çağırıp veritabanına kaydediyoruz
    return crud.create_user(db=db, user=user)

# 2. Belirli Bir Kullanıcıyı ID'sine Göre Getirme (Profil Görüntüleme)
@router.get("/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        # Eğer o ID'de bir kullanıcı yoksa 404 Not Found hatası ver
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

# 3. Kullanıcıları listele (Read - Çoklu)
@router.get("/", response_model=list[schemas.UserResponse])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_users(db=db, skip=skip, limit=limit)

# 4. Kullanıcıyı güncelle (Update)
@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, user: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud.update_user(db=db, user_id=user_id, user_update=user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return db_user

# 5. Kullanıcıyı sil (Delete)
@router.delete("/{user_id}", response_model=schemas.UserResponse)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.delete_user(db=db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return db_user