FROM python:3.11-slim
LABEL description="Pipeline API — voiceover + quality check + publisher + analytics"
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y \
    ffmpeg libgl1 libglib2.0-0 curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi uvicorn \
    elevenlabs gtts yt-dlp \
    httpx \
    google-api-python-client google-auth-oauthlib google-auth-httplib2 \
    boto3
# Copy all pipeline modules
COPY voiceover/    /app/voiceover/
COPY publisher/    /app/publisher/
COPY quality-check/ /app/quality_check/
COPY analytics/    /app/analytics/
COPY analytics-dashboard/ /app/dashboard/
COPY yt-pipeline/ /app/yt_pipeline/
COPY pipeline.py   /app/pipeline.py
COPY pipeline-api/main.py /app/main.py
RUN touch /app/voiceover/__init__.py /app/publisher/__init__.py \
          /app/quality_check/__init__.py /app/analytics/__init__.py \
          /app/yt_pipeline/__init__.py
RUN mkdir -p /videos /output /app/credentials
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
