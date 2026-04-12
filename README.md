# RecruitAssistant-Back

AI-powered recruitment platform backend built with FastAPI and PostgreSQL.

# To run locally without Docker
pip install -r requirements.txt

# Required locally for PDF generation
brew install tectonic
   
uvicorn main:app --reload

# To run/deploy with Docker
The deployed backend needs the **Tectonic** binary for CV/Cover Letter PDF generation. `requirements.txt` only installs Python packages, so deployment should use the Dockerfile instead of a plain Python build.

```bash
docker build -t recruitassistant-back .
docker run --env-file .env -p 8000:8000 recruitassistant-back
```

In Docker, do not run `pip install -r requirements.txt` manually on the server. The Dockerfile already runs it inside the image and also installs `tectonic` at `/usr/local/bin/tectonic`, matching the local PDF generation behavior.

# To update database
alembic revision --autogenerate -m "Describe your changes here"
alembic upgrade head

---

## 🚀 Yenilikler ve Önemli Notlar (Ekip İçin)

### 1. Sistem Gereksinimi: Tectonic (Kritik)
CV'leri PDF'e dönüştürebilmek için Docker kullanmadan çalışan lokal geliştirme bilgisayarınızda **Tectonic** yüklü olmalıdır. Mac kullananlar için:
```bash
brew install tectonic
```

Deployment için Docker kullanıyorsanız ayrıca Tectonic kurmanıza gerek yoktur; Dockerfile image içine kurar.

### 2. Otomatik Veritabanı Migration
Backend'i başlattığınızda (`uvicorn`), veritabanı şeması (yeni eklenen sütunlar, kısıtlamalar vb.) otomatik olarak kontrol edilir ve güncellenir. Manuel `migrate_db.py` çalıştırmanıza gerek yoktur, sistem açılışta bunu halleder.

### 3. Default User
Sistem ilk açılışta `id=1` olan bir kullanıcı yoksa otomatik oluşturur. Bu sayede test yaparken kullanıcı hatası almazsınız.
