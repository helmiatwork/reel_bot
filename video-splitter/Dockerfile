FROM python:3.11-slim
LABEL description="video-splitter — split long videos into chunks"
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y ffmpeg git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN git clone https://github.com/c0decracker/video-splitter.git . && git checkout master
RUN pip install --no-cache-dir requests
RUN mkdir -p /videos
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]
