FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY reference/fw309-register-matrix.json \
     reference/fw309_anlage21.json \
     reference/golden-comparison-map.json \
     /app/reference/
RUN pip install --no-cache-dir '.[serial]'

ARG GATEWAY_UID=1000
ARG GATEWAY_GID=1000

RUN set -eux; \
    if getent group "${GATEWAY_GID}" >/dev/null; then \
        gateway_group="$(getent group "${GATEWAY_GID}" | cut -d: -f1)"; \
    else \
        groupadd --gid "${GATEWAY_GID}" gateway; \
        gateway_group=gateway; \
    fi; \
    useradd --uid "${GATEWAY_UID}" --gid "${gateway_group}" \
        --create-home --shell /usr/sbin/nologin gateway; \
    mkdir -p /data; \
    chown "${GATEWAY_UID}:${GATEWAY_GID}" /data
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
