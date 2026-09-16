# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ARG TARGETARCH
ARG TTYD_VERSION=1.7.7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git gettext-base nano nginx-light procps tini tmux \
    && rm -rf /var/lib/apt/lists/*

# Optional browser terminal. Download a tiny static ttyd binary and verify it against upstream checksums.
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) TTYD_ARCH=x86_64 ;; \
      arm64) TTYD_ARCH=aarch64 ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    BASE="https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}"; \
    curl -fsSLo /tmp/ttyd "${BASE}/ttyd.${TTYD_ARCH}"; \
    curl -fsSLo /tmp/SHA256SUMS "${BASE}/SHA256SUMS"; \
    EXPECTED="$(awk -v f="ttyd.${TTYD_ARCH}" '$2==f {print $1}' /tmp/SHA256SUMS)"; \
    test -n "$EXPECTED"; \
    echo "$EXPECTED  /tmp/ttyd" | sha256sum -c -; \
    install -m 0755 /tmp/ttyd /usr/local/bin/ttyd; \
    rm -f /tmp/ttyd /tmp/SHA256SUMS

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash app \
    && mkdir -p /app /workspace /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi \
    && chown -R app:app /app /workspace /tmp/nginx-*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY config /app/config
COPY examples /app/examples
COPY scripts /app/scripts
COPY nginx /app/nginx
RUN chmod +x /app/scripts/*.sh && chown -R app:app /app /workspace

USER app
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-10000}/healthz" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
