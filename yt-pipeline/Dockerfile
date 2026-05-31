FROM python:3.11-slim
LABEL description="yt-pipeline — YouTube research + transcript + script generation"
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y \
    ffmpeg libgl1-mesa-glx libglib2.0-0 git curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir yt-dlp httpx openai-whisper
RUN git clone https://github.com/byjlw/video-analyzer.git /tmp/va \
    && cd /tmp/va && pip install --no-cache-dir . && rm -rf /tmp/va
RUN python3 -c "import whisper; whisper.load_model('base')"
COPY yt_pipeline.py /app/yt_pipeline.py
RUN mkdir -p /videos /output
ENV CLIPROXY_URL=http://cliproxy:8317/v1 CLIPROXY_KEY=local-proxy-key
ENV PEXELS_API_KEY="" FREESOUND_API_KEY=""
ENTRYPOINT ["python3", "/app/yt_pipeline.py"]
CMD ["--help"]
