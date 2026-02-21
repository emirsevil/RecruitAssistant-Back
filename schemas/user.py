from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# 1. Ortak Özellikler (Hem veri eklerken hem okurken ortak olanlar)
class UserBase(BaseModel):
    full_name: str
    email: EmailStr # EmailStr formatın gerçekten "x@y.com" olmasını zorunlu kılar
    university: Optional[str] = None

# 2. Veri Eklerken (Create) Kullanılacak Şema
# React'ten bize kullanıcı kaydolurken gelecek verilerin şablonu.
# İleride buraya 'password' alanı da ekleyeceğiz.
class UserCreate(UserBase):
    pass 

# 3. Veri Okurken (Response/Read) Kullanılacak Şema
# Veritabanından veriyi çekip React'e gönderirken bu şablonu kullanacağız.
class UserResponse(UserBase):
    id: int
    created_at: datetime

    # SQLAlchemy modelleriyle uyumlu çalışabilmesi için gereken ayar:
    model_config = {"from_attributes": True}