#!/usr/bin/env bash
set -Eeuo pipefail
# Run against a local Docker container to verify restart behavior and health endpoints.
# 1) Start TitanBox with ENABLE_RUNNER=true and enable dummy-worker in config/apps.toml.
# 2) Kill the child worker from /admin/status PID.
# 3) Verify AppRunner restarts it and restart_count increments.
echo "See docs/TESTING.md for the automated test suite and chaos checklist."
