from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    education: Optional[str] = None # Added education, removed university
    phone: Optional[str] = None
    address: Optional[str] = None
    bio: Optional[str] = None
    professional_title: Optional[str] = None
    skills: Optional[str] = None
    profile_image: Optional[str] = None
    base_cv: Optional[str] = None
    is_searchable: Optional[bool] = None  # Candidate consent for recruiter visibility

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    education: Optional[str] = None # Added education, removed university
    phone: Optional[str] = None
    address: Optional[str] = None
    bio: Optional[str] = None
    professional_title: Optional[str] = None
    skills: Optional[str] = None
    profile_image: Optional[str] = None
    base_cv: Optional[str] = None
    is_searchable: Optional[bool] = None  # Toggle recruiter visibility

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None