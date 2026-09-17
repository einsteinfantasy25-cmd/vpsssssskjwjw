#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${1:-http://127.0.0.1:10000}"
WAIT_SECONDS="${SMOKE_WAIT_SECONDS:-45}"

wait_for() {
  local path="$1"
  local deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 5 "${BASE_URL}${path}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "smoke test: timed out waiting for ${path}" >&2
  return 1
}

# /healthz is local liveness and should become available first. /readyz can legitimately
# remain 503 for a few seconds while required PostgreSQL/S3 cold-start checks finish.
wait_for /healthz
wait_for /readyz

# /wakez is intentionally lightweight and does not touch external persistence.
if ! curl -fsS --max-time 5 "${BASE_URL}/wakez" >/dev/null 2>&1; then
  echo "smoke test: /wakez unavailable (WAKE_ENDPOINT_ENABLED may be false)" >&2
fi

echo "smoke test: PASS"
