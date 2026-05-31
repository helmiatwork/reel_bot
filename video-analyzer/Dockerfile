FROM python:3.11-slim
LABEL description="video-analyzer — frame analysis via vision AI"
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y \
    ffmpeg libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev git curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# CPU-only PyTorch — saves ~2GB vs CUDA version
RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu
RUN git clone https://github.com/byjlw/video-analyzer.git . && git checkout main
RUN pip install --no-cache-dir .
# Pre-download Whisper base model during build
RUN python3 -c "import whisper; whisper.load_model('base')"
RUN mkdir -p /videos /output
ENV CLIPROXY_URL=http://cliproxy:8317/v1 CLIPROXY_KEY=local-proxy-key
ENV MODEL=gemini/gemini-2.5-flash-lite WHISPER_MODEL=base
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]
