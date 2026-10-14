FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng libreoffice ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY AI_Engine ./AI_Engine
RUN mkdir -p /state/data && chown -R app:app /state
USER app
CMD ["python", "-m", "uvicorn", "AI_Engine.router:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
