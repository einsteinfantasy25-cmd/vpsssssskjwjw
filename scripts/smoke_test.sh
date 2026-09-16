#!/usr/bin/env bash
set -Eeuo pipefail
BASE_URL="${1:-http://127.0.0.1:10000}"
curl -fsS "$BASE_URL/healthz" >/dev/null
curl -fsS "$BASE_URL/readyz" >/dev/null
curl -fsS "$BASE_URL/metrics" | grep -q '^titanbox_up 1$'
echo "smoke test: PASS"
