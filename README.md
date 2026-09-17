# TitanBox v0.4.0 HARDENED

TitanBox is a lightweight Telegram control plane/runtime for small PaaS containers such as Render and Railway. v0.4 focuses on **security, failure containment, diagnostics, release integrity and beginner-safe deployment**.

## Hardened defaults

- non-root container
- Telegram webhook secret verification
- automatic webhook registration + self-healing watchdog
- global and per-bot concurrency limits
- per-bot token-bucket rate limit
- per-bot failure circuit breaker
- bounded retry-safe update de-duplication
- memory-pressure backpressure
- streamed request body size limits
- secret redaction in logs/errors
- Deploy Admin Telegram allowlist
- optional TOTP 2FA for sensitive admin actions
- append-only HMAC-chained audit log
- transactional releases + rollback
- per-release SHA-256 integrity manifest
- no hard links between rollback releases
- Zip Slip/symlink/path/duplicate-normalized-path/count/expanded-size protections
- public status details hidden by default
- Admin HTTP API disabled by default
- metrics protected by default
- `CONTROL_PLANE_ONLY=true` + `MAX_BOTS_PER_RUNTIME=1` on the Render admin service
- GitHub Actions tests, repository secret scan, dependency audit, Docker smoke build and CodeQL

## Important boundaries

TitanBox is **not a fake VPS** and does not create CPU/RAM. Ultra Mode plugins in one Python process are not a hard security boundary. For strict bot-to-bot isolation, deploy each important bot as a separate platform service/container with its own token, DB role and storage credentials.

Render Free local filesystem is ephemeral. Code/data that must survive restart/redeploy/spin-down belongs in Git/external DB/object storage.

Arabic beginner guide: **`START_HERE_AR.md`**.
