# TitanBox v1.0.0 FINAL

TitanBox is a hardened Telegram **control plane** for small PaaS containers such as Render. It is designed to keep the Deploy Admin bot isolated, recover safely from cold starts, persist important deployment state outside the ephemeral container, and fail closed when required infrastructure is unavailable.

## What v1 adds

- S3-compatible durable release storage (Cloudflare R2 / Backblaze B2 / AWS S3 / MinIO-compatible APIs)
- two-phase release backup: candidate -> local validation/health -> signed active backup
- SHA-256 archive verification plus optional HMAC authenticity using `RELEASE_SIGNING_KEY`
- PostgreSQL control-plane tables for metadata, mirrored audit records, idempotency and a persistent admin job queue
- deploy/restart/rollback/restore jobs can be committed to PostgreSQL before execution, then resumed after a process/container interruption
- `/infra`, `/setup`, `/jobs`, `/backups`, `/restore`, `/wake`
- lightweight `/wakez` endpoint and background Telegram webhook registration for cold-start-friendly boot
- webhook self-healing watchdog
- Render control-plane guard: `CONTROL_PLANE_ONLY=true` + `MAX_BOTS_PER_RUNTIME=1`
- non-root container, secret redaction, webhook secret verification, per-bot rate/concurrency limits, circuit breaker, cgroup memory backpressure
- TOTP 2FA for sensitive admin operations, HMAC-chained audit log, release integrity manifests and safe rollback
- GitHub CI / CodeQL / dependency audit / secret scan / Docker smoke build

## Important truths

TitanBox is **not a VPS** and does not create CPU/RAM that the platform did not allocate.

Render Free local storage is ephemeral. Durable state belongs in Git, PostgreSQL and object storage. v1 can use external storage/DB, but you must create those provider accounts and place their credentials in Render Environment variables; no real credentials are committed to this repository.

Render Free can sleep on idle. TitanBox does not self-ping or attempt to defeat provider limits. The Telegram webhook or `/wakez` can wake the service on demand, and the runtime is designed to recover cleanly from that cold start. If you need consistently warm, low-latency service, use always-on compute.

For hard bot-to-bot isolation, keep this service as Deploy Admin only and deploy every important student/public bot in its own service/container with its own token, database role and storage credentials.

Start with **`FINAL_SETUP_AR.md`** (Arabic beginner walkthrough).

## Reliability model

When PostgreSQL is configured, Deploy Admin mutations are persisted before execution and recovered after worker loss using leases/retries. Deployment side effects are designed to be idempotent and rollback/restore targets are frozen before queuing. This is an at-least-once + idempotency design; TitanBox does not claim impossible cross-provider distributed exactly-once execution.

Durable release state uses candidate -> local health verification -> signed active marker. The signed latest pointer and active markers are verified before restore, and a stale pointer can be repaired from valid active markers.
