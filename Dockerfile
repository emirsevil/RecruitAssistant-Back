FROM rust:1.85-bookworm AS tectonic-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        clang \
        cmake \
        libfontconfig1-dev \
        libfreetype6-dev \
        libharfbuzz-dev \
        libicu-dev \
        libpng-dev \
        libssl-dev \
        make \
        pkg-config \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN cargo install tectonic --version 0.15.0

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libfontconfig1 \
        libfreetype6 \
        libgraphite2-3 \
        libharfbuzz0b \
        libicu72 \
        libpng16-16 \
        libssl3 \
        libstdc++6 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tectonic-builder /usr/local/cargo/bin/tectonic /usr/local/bin/tectonic

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN tectonic --version \
    && mkdir -p /tmp/tectonic-smoke \
    && printf '\\documentclass{article}\\begin{document}RecruitAssistant PDF smoke test\\end{document}' > /tmp/tectonic-smoke/smoke.tex \
    && tectonic -X compile /tmp/tectonic-smoke/smoke.tex --outdir /tmp/tectonic-smoke \
    && rm -rf /tmp/tectonic-smoke

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
