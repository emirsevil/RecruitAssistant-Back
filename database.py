from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# 1. .env dosyasını oku
load_dotenv()

# 2. Adresi al
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./test.db"

# 3. Motoru (Engine) oluştur. Bu, veritabanına giden tüneldir.
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 4. Oturum (Session) oluşturucu. Veritabanı ile her işlemde bir session açarız.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Modellerimizin (Tablolarımızın) türeyeceği ana sınıf
Base = declarative_base()

# 6. Bağlantıyı güvenli açıp kapatan fonksiyon (Dependency Injection için)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()