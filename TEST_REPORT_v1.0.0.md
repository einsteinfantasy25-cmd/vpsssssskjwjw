# TitanBox v1.0.0 FINAL — Test Report

Build date: 2026-09-17.

## Automated suite

- **101 tests passed** in the local build environment.
- `python scripts/preflight_repo.py`: passed.
- `python scripts/secret_scan.py .`: passed.
- `python -m compileall -q src tests scripts examples`: passed.
- Bash syntax for entrypoint/smoke/chaos scripts: passed.
- `render.yaml`: parsed successfully as YAML in the build environment.

The suite covers previous hardening plus v1 persistence scenarios including:

- S3 candidate backup is not restorable until promotion.
- active backup/archive integrity verification.
- corrupted remote archive rejection.
- abandoned candidate exclusion.
- HMAC metadata/active-marker tamper detection.
- required durable backup failure blocking activation.
- required durable promotion failure restoring previous state.
- first-deploy runtime failure leaving no bad `current` pointer.
- safe adaptive defaults: configured S3/PostgreSQL become required unless explicitly overridden.
- release signing key inclusion in secret redaction.
- persistent document operation enqueued before execution and resumable through the worker path.
- `/setup` does not echo storage credentials.
- `/wakez` response contract.
- deterministic Deploy/Put/Restore operation IDs survive persistent-job replay without duplicate releases.
- queued smart updates freeze project/path before Render can lose in-memory `/use` state.
- rollback target and durable `latest` restore target are frozen before enqueue.
- signed durable-release ordering uses activation time instead of release-name ordering.
- stale latest-pointer recovery/self-heal and signed-pointer tamper rejection.
- durable restore has a bounded internal size path independent of Telegram's upload ceiling.
- PostgreSQL pool startup is serialized across cold-start races.
- custom S3 endpoints default to path-style with explicit override support.

## Live ASGI smoke test

A real Uvicorn process was started with storage/database disabled and no Telegram bot configured.

Verified:

```text
/healthz -> 200, version=1.0.0
/wakez   -> 200, awake=true
/status  -> 200
/readyz  -> 200
```

## Webhook stress smoke test

A real TitanBox Uvicorn process loaded a temporary local bot plugin with webhook authentication enabled. The real `/telegram/loadbot` route received **1,500 unique webhook updates at concurrency 50**.

Observed in this build environment:

```text
requests:        1500
concurrency:     50
failures:        0
throughput:      ~270.6 req/s
p50:             ~110.0 ms
p95:             ~536.9 ms
p99:             ~930.7 ms
wrong secret:    HTTP 403
```

These numbers are **not a Render Free capacity guarantee**. CPU scheduling, network latency, cold starts and platform resource limits differ. The useful result is zero failures through the authenticated webhook path and correct rejection of the wrong webhook secret.

## Build limitation

The sandbox did not have `ruff` installed and did not provide a Docker engine or outbound package installation. The GitHub CI in this repository installs `requirements-dev.txt`, runs `ruff`, dependency audit and the real Docker image build/smoke test on every push/PR.
