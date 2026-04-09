# RecruitAssistant-Back

AI-powered recruitment platform backend built with FastAPI and PostgreSQL.

# To run
pip install -r requirements.txt
   
uvicorn main:app --reload

# To update database
alembic revision --autogenerate -m "Describe your changes here"
alembic upgrade head

---

## 🚀 Yenilikler ve Önemli Notlar (Ekip İçin)

### 1. Sistem Gereksinimi: Tectonic (Kritik)
CV'leri PDF'e dönüştürebilmek için bilgisayarınızda **Tectonic** yüklü olmalıdır. Mac kullananlar için:
```bash
brew install tectonic
```

### 2. Otomatik Veritabanı Migration
Backend'i başlattığınızda (`uvicorn`), veritabanı şeması (yeni eklenen sütunlar, kısıtlamalar vb.) otomatik olarak kontrol edilir ve güncellenir. Manuel `migrate_db.py` çalıştırmanıza gerek yoktur, sistem açılışta bunu halleder.

### 3. Default User
Sistem ilk açılışta `id=1` olan bir kullanıcı yoksa otomatik oluşturur. Bu sayede test yaparken kullanıcı hatası almazsınız.
