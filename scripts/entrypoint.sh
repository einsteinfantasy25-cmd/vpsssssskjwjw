#!/usr/bin/env bash
set -Eeuo pipefail

export PORT="${PORT:-10000}"
export HOST="${HOST:-0.0.0.0}"
export PYTHONPATH="${PYTHONPATH:-/app/src}"
export UVICORN_LIMIT_CONCURRENCY="${UVICORN_LIMIT_CONCURRENCY:-100}"
export UVICORN_KEEP_ALIVE="${UVICORN_KEEP_ALIVE:-5}"

cleanup() {
  set +e
  for pid in "${NGINX_PID:-}" "${TTYD_PID:-}" "${API_PID:-}"; do
    if [[ -n "$pid" ]]; then kill -TERM "$pid" 2>/dev/null || true; fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ "${ENABLE_TERMINAL:-false}" =~ ^(1|true|TRUE|yes|on)$ ]]; then
  if ! command -v ttyd >/dev/null 2>&1 || ! command -v nginx >/dev/null 2>&1; then
    echo "ENABLE_TERMINAL=true but the hardened Dockerfile intentionally excludes ttyd/nginx." >&2
    echo "Use Dockerfile.terminal only when you explicitly accept the larger attack surface." >&2
    exit 64
  fi
  : "${TERMINAL_USER:?TERMINAL_USER is required when ENABLE_TERMINAL=true}"
  : "${TERMINAL_PASSWORD:?TERMINAL_PASSWORD is required when ENABLE_TERMINAL=true}"
  if (( ${#TERMINAL_PASSWORD} < 16 )); then
    echo "TERMINAL_PASSWORD must be at least 16 characters" >&2
    exit 64
  fi

  uvicorn titanbox.main:app --host 127.0.0.1 --port 8080 --workers 1 --no-access-log --no-server-header \
    --limit-concurrency "$UVICORN_LIMIT_CONCURRENCY" --timeout-keep-alive "$UVICORN_KEEP_ALIVE" &
  API_PID=$!

  ttyd -i 127.0.0.1 -p 7681 -b /terminal -W -O \
    -m "${TERMINAL_MAX_CLIENTS:-1}" \
    -c "${TERMINAL_USER}:${TERMINAL_PASSWORD}" \
    -w /workspace bash -l &
  TTYD_PID=$!

  envsubst '${PORT}' < /app/nginx/nginx.conf.template > /tmp/nginx.conf
  nginx -c /tmp/nginx.conf -g 'daemon off;' &
  NGINX_PID=$!

  wait -n "$API_PID" "$TTYD_PID" "$NGINX_PID"
  echo "A TitanBox child process exited; stopping container for a clean platform restart." >&2
  exit 1
else
  exec uvicorn titanbox.main:app --host "$HOST" --port "$PORT" --workers 1 --no-access-log --no-server-header \
    --limit-concurrency "$UVICORN_LIMIT_CONCURRENCY" --timeout-keep-alive "$UVICORN_KEEP_ALIVE"
fi
