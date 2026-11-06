FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir '.[serial]'

RUN useradd --system --uid 10001 --create-home gateway \
    && mkdir -p /data \
    && chown gateway:gateway /data
USER gateway

ENV LISTEN_ADDRESS=0.0.0.0 \
    LISTEN_PORT=7112 \
    ADMIN_ADDRESS=0.0.0.0 \
    ADMIN_PORT=8080 \
    GATEWAY_CONFIG_PATH=/data/config.json
EXPOSE 7112 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]
ENTRYPOINT ["trovis-gateway"]
