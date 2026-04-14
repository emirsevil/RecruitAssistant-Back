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
    hashed_password = Column(String, nullable=True) # Will be made non-nullable after migration
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    professional_title = Column(String, nullable=True)
    education = Column(Text, nullable=True) # Replaces university with more detail
    skills = Column(Text, nullable=True)
    profile_image = Column(String, nullable=True) # URL for profile picture
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    cvs = relationship("CV", back_populates="owner")
    workspaces = relationship("Workspace", back_populates="owner")
    quiz_scores = relationship("QuizScore", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")

# 2. CV (Özgeçmişler Tablosu)
class CV(Base):
    __tablename__ = "cvs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_url = Column(String, nullable=True)  # URL for uploaded CVs
    latex_content = Column(Text, nullable=True)  # LaTeX source for AI-generated CVs
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
    job_name = Column(String, nullable=True) # Eklendi
    emoji = Column(String, nullable=True) # Eklendi
    color = Column(String, nullable=True) # Eklendi
    job_description = Column(Text, nullable=True)
    generated_cv_id = Column(Integer, ForeignKey("cvs.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    owner = relationship("User", back_populates="workspaces")
    generated_cv = relationship("CV", foreign_keys=[generated_cv_id], uselist=False)
    quizzes = relationship("Quiz", back_populates="workspace")
    interviews = relationship("Interview", back_populates="workspace")
    cover_letters = relationship("CoverLetter", back_populates="workspace")

# 4. COVER LETTER (Niyet Mektupları Tablosu) - YENİ EKLENDİ
class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    content = Column(Text, nullable=False)  # Yapay zekanın ürettiği mektubun metni
    latex_content = Column(Text, nullable=True)  # LaTeX source for AI-generated cover letters
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    workspace = relationship("Workspace", back_populates="cover_letters")

# 5. QUIZ (Sınavlar Tablosu - Gruplama Üst Tablosu)
class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    title = Column(String, nullable=True) # Konu başlığı (Örn: SQL, Java)
    difficulty = Column(String, nullable=True) # Zorluk seviyesi: Easy, Medium, Hard
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    workspace = relationship("Workspace", back_populates="quizzes")
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    quiz_scores = relationship("QuizScore", back_populates="quiz", cascade="all, delete-orphan")

# 5.1. QUESTION (Sınav Soruları Tablosu)
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=True)
    
    question = Column(String, nullable=False)
    options = Column(JSON, nullable=False)  
    correct_answer = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quiz = relationship("Quiz", back_populates="questions")

# 6. INTERVIEW (Mülakatlar Tablosu)
class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    interview_type = Column(String, nullable=False)  # "technical" or "hr"
    feedback = Column(Text, nullable=True)            # JSON: evaluation results
    transcript = Column(Text, nullable=True)          # JSON: questions list or conversation
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # New metadata columns
    difficulty = Column(String, nullable=True)         # "intern", "junior", "mid"
    categories = Column(String, nullable=True)         # Topics/categories used
    overall_score = Column(Integer, nullable=True)     # 0-100 overall score
    duration_seconds = Column(Integer, nullable=True)  # Interview duration in seconds
    status = Column(String, nullable=False, default="in_progress")  # "in_progress", "completed", "cancelled"
    mode = Column(String, nullable=False, default="text")            # "text" or "voice"

    # İlişkiler
    workspace = relationship("Workspace", back_populates="interviews")

# 7. QUIZ SCORE (Quiz Sonuçları Tablosu)
class QuizScore(Base):
    __tablename__ = "quiz_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    
    score = Column(Integer, nullable=False)  # Yüzdelik skor (0-100)
    attempt_number = Column(Integer, nullable=False, default=1) # 1, 2 veya 3
    total_questions = Column(Integer, nullable=False)
    correct_answers = Column(Integer, nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    user = relationship("User", back_populates="quiz_scores")
    quiz = relationship("Quiz", back_populates="quiz_scores")

# 8. REFRESH TOKEN (Oturum Yenileme Token Tablosu)
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    login_time = Column(DateTime(timezone=True), nullable=False)   # Hard limit hesabı
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    user = relationship("User", back_populates="refresh_tokens")