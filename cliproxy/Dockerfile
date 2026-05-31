FROM ubuntu:24.04
LABEL description="CLIProxyAPI — AI model proxy to Sumopod"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Copy binary + config from host (run: scp ~/cliproxyapi/cli-proxy-api user@VPS:./cliproxy/)
COPY cli-proxy-api /app/cli-proxy-api
COPY config.yaml   /app/config.yaml
RUN chmod +x /app/cli-proxy-api
EXPOSE 8317
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8317 || exit 1
CMD ["/app/cli-proxy-api", "-config", "/app/config.yaml"]
