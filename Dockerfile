# ─────────────────────────────────────────────────────
#  RecruitAssistant Backend — Production Dockerfile
#  Includes TeX Live for pdflatex compilation
# ─────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ──────────────────────────────
# texlive-latex-base  → pdflatex binary
# texlive-latex-extra → extra packages (geometry, parskip, etc.)
# texlive-fonts-recommended → standard fonts
# cm-super            → Computer Modern fonts in Type1 format
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-latex-recommended \
        cm-super \
        lmodern \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify pdflatex is available
RUN pdflatex --version

# ── Application ──────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── Runtime ──────────────────────────────────────────
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
