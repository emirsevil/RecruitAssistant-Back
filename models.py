from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"  # Veritabanında tablonun adı 'users' olacak

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)