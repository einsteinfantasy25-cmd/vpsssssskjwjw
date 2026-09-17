# TitanBox v0.4.0 HARDENED — Test Report

Tested in the build environment on 2026-09-17.

## Automated verification

- **67 unit/integration tests passed**.
- `python scripts/preflight_repo.py` passed (14 mandatory release paths present).
- `python scripts/secret_scan.py` passed (no obvious committed high-impact credentials).
- `python -m compileall -q src tests examples` passed.
- Bash syntax checks passed for entrypoint, smoke test and manual chaos script.
- GitHub CI is configured to run Ruff, tests on Python 3.12/3.13, pip-audit, CodeQL, Docker Buildx and a real image `/healthz` smoke test.

`ruff` was not installed in this local sandbox, so the local report does not claim a local Ruff run; the included CI runs it after push.

## Security/failure scenarios covered

- missing/invalid configuration and bot secrets;
- webhook secret authentication;
- Telegram-token error redaction;
- bounded/streamed webhook body handling;
- update dedupe including retry-safe in-flight duplicate handling;
- per-bot rate limiting and failure circuit behavior;
- Admin API hidden/authenticated behavior;
- Deploy Admin allowlist/private-chat/edited-update behavior;
- TOTP generation/verification/replay rejection and 2FA command gating;
- audit-chain tamper detection;
- safe ZIP extraction: traversal, symlink, count/size, duplicate normalized paths, invisible Unicode;
- malformed Python/JSON/TOML rejection;
- transactional deploy/update/rollback;
- release SHA-256 manifest tamper detection;
- independent rollback files (no cross-release hard links);
- serialized concurrent project updates;
- runner normal/crash-loop behavior and committed-secret rejection;
- Render release contract/control-plane configuration.

## Live runtime smoke/load test

A real local Uvicorn v0.4.0 process was started with one no-op Telegram webhook path. 1,500 unique authenticated webhook requests were sent at concurrency 50.

Observed in this build environment:

```text
requests: 1500
concurrency: 50
failures: 0
elapsed: 5.569 s
throughput: ~269.3 req/s
p50: ~112.6 ms
p95: ~546.8 ms
p99: ~843.9 ms
```

The public `/status` during the run returned version 0.4.0, one configured bot, one loaded bot, and `bots_ready=true`, with bot details hidden as designed.

These numbers are **not Render Free capacity guarantees**. The useful result is zero failures in this smoke workload and correct containment/public-status behavior.

## Architectural limits intentionally not misrepresented

This test suite cannot turn shared-process plugins into hard isolation, cannot make Render Free filesystem persistent, and cannot provide provider-level DDoS protection or durable external backups without external infrastructure. Those are documented separately.
