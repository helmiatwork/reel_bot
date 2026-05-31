FROM node:24-slim
LABEL description="OpenClaw — AI agent + Telegram entry point"
ENV DEBIAN_FRONTEND=noninteractive NODE_ENV=production
RUN apt-get update && apt-get install -y curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN npm install -g openclaw
WORKDIR /root/.openclaw
VOLUME ["/root/.openclaw", "/videos"]
EXPOSE 18789
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:18789 || exit 1
CMD ["openclaw", "gateway", "--port", "18789"]
