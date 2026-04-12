from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# 1. .env dosyasını oku
load_dotenv()

# 2. Adresi al ve temizle (tırnak işaretlerini kaldır)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.strip().strip('"').strip("'")
    
    # [Yeni Hibrit Mantık]: Docker dışında çalışıyorsak adresi localhost'a çevir
    if not os.path.exists("/.dockerenv") and "host.docker.internal" in SQLALCHEMY_DATABASE_URL:
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("host.docker.internal", "localhost")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL ortam değişkeni bulunamadı veya boş! Lütfen .env dosyanızı veya Docker ortam değişkenlerinizi kontrol edin.")

# 3. Motoru (Engine) oluştur.
try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
except Exception as e:
    print(f"\n[HATA] SQLAlchemy URL ayrıştırılamadı: {SQLALCHEMY_DATABASE_URL}")
    print(f"[İPUÇU] URL formatı doğru mu? Örn: postgresql://user:pass@host:port/db")
    raise e

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