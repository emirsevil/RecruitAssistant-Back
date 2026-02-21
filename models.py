from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 1. USER (Kullanıcı Tablosu)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    university = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    cvs = relationship("CV", back_populates="owner")
    workspaces = relationship("Workspace", back_populates="owner")

# 2. CV (Özgeçmişler Tablosu)
class CV(Base):
    __tablename__ = "cvs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_url = Column(String, nullable=False)
    is_base_cv = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    owner = relationship("User", back_populates="cvs")

# 3. WORKSPACE (Çalışma Alanı Tablosu - Ana Merkez)
class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_name = Column(String, nullable=False)
    job_description = Column(Text, nullable=True)
    generated_cv_id = Column(Integer, ForeignKey("cvs.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    owner = relationship("User", back_populates="workspaces")
    quizzes = relationship("Quiz", back_populates="workspace")
    interviews = relationship("Interview", back_populates="workspace")
    cover_letters = relationship("CoverLetter", back_populates="workspace") # YENİ EKLENDİ

# 4. COVER LETTER (Niyet Mektupları Tablosu) - YENİ EKLENDİ
class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    content = Column(Text, nullable=False) # Yapay zekanın ürettiği mektubun metni
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    workspace = relationship("Workspace", back_populates="cover_letters")

# 5. QUIZ (Sınavlar Tablosu)
class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    # Genel quizler için null kalabilir, o yüzden nullable=True yapıyoruz
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True) 
    
    question = Column(String, nullable=False)
    # Şıkları ["A", "B", "C", "D"] şeklinde liste olarak tutmak için JSON kullanıyoruz
    options = Column(JSON, nullable=False)  
    correct_answer = Column(String, nullable=False)

    workspace = relationship("Workspace", back_populates="quizzes")

# 6. INTERVIEW (Mülakatlar Tablosu)
class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    interview_type = Column(String, nullable=False) # "Technical" veya "HR"
    feedback = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    workspace = relationship("Workspace", back_populates="interviews")