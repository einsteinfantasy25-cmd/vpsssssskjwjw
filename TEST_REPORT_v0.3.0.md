# TitanBox v0.3.0 — Test Report

## Local automated tests

Result at release packaging time:

```text
45 passed
```

Coverage areas include:

- settings parsing and validation
- Render URL auto-detection
- Admin ID parsing and legacy `0` handling
- webhook secret derivation
- wrong webhook secret rejection
- two-phase Telegram update deduplication
- retry of failed updates
- missing bot token isolation
- automatic webhook registration verification with mocked Telegram API
- invalid Telegram token error redaction (token must never appear in diagnostics)
- Deploy Admin authorization/discovery flow
- `/diag`
- safe ZIP extraction
- zip traversal rejection
- symlink rejection
- Python/JSON/TOML validation
- single-file updates
- release/rollback behavior
- runner crash/restart behavior
- API health/readiness/dashboard
- required repository tree contract
- Render Blueprint regression checks
- Dockerfile build-context regression checks

## Static/syntax checks

Passed:

```text
python scripts/preflight_repo.py
python -m compileall -q src tests scripts examples
bash -n scripts/entrypoint.sh scripts/smoke_test.sh tests/chaos/manual_chaos.sh
```

## Live process smoke test

TitanBox v0.3.0 was launched with Uvicorn and verified for:

```text
/healthz = 200
/readyz  = 200 with zero configured bots
/status  = valid JSON
/        = HTML dashboard
```

A deliberate missing-token configuration was also launched. Expected behavior was confirmed:

```text
/healthz = 200
/readyz  = 503
/status  = explicit "missing environment secret" error
```

This is intentional: a bot configuration error remains diagnosable without making the whole web service disappear.

## Local HTTP load smoke

A local Uvicorn process received 1,500 `/healthz` requests at concurrency 50:

```text
failures=0
throughput≈279.7 req/s
p50≈108.7 ms
p95≈515.1 ms
p99≈783.3 ms
```

These are sandbox numbers, not a promise of Render Free performance. Their purpose is regression/stability testing of the control-plane endpoint.

## CI-only checks

GitHub Actions is configured to run Ruff, dependency audit, tests, compilation and a Docker build on GitHub infrastructure. Ruff could not be installed inside the packaging sandbox because that sandbox had no package-network access; it remains enforced in the repository CI workflow.
