# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    PYTHONPATH=/app/src

# Hardened default image: no SSH, VNC, browser terminal, nginx, tmux, editor, or Docker daemon.
RUN apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash app \
    && mkdir -p /app /workspace \
    && chown -R app:app /app /workspace

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=app:app . /app
RUN set -eu; \
    missing=""; \
    for p in src/titanbox/main.py src/titanbox/settings.py src/titanbox/security.py src/titanbox/audit.py src/titanbox/storage.py src/titanbox/database.py src/titanbox/infrastructure.py src/titanbox/plugins/deploy_admin.py scripts/entrypoint.sh scripts/generate_totp.py config/apps.toml; do \
      if [ ! -e "/app/$p" ]; then missing="$missing $p"; fi; \
    done; \
    if [ -n "$missing" ]; then \
      echo "FATAL: TitanBox repository is incomplete. Missing:$missing" >&2; \
      echo "Upload the FULL project root to GitHub, not only the top-level files." >&2; \
      exit 64; \
    fi; \
    chmod +x /app/scripts/*.sh /app/scripts/generate_totp.py; \
    chown -R app:app /app /workspace

USER app
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-10000}/healthz" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
