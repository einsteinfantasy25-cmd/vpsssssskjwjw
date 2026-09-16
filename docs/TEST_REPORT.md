# TitanBox v0.2.0 test report

Tested in the build environment on 2026-09-15.

## Automated suite

- **33 unit/integration tests passed**.
- Python compile check (`compileall`) passed for `src`, `tests`, and scripts.
- Bash syntax checks passed for entrypoint, smoke test, and chaos script.
- Generated Nginx configuration passed `nginx -t`.

The automated suite covers, among other cases:

- webhook authentication and two-phase Telegram update deduplication;
- admin API authentication;
- Legacy Runner normal exit and crash-loop circuit breaker;
- Deploy Admin allowlist requirement;
- safe ZIP deployment and single-file update;
- smart basename lookup for file replacement;
- rollback to a previous release;
- automatic restoration of the previous release when the updated app fails to stabilize;
- malformed Python syntax never becoming current;
- malformed JSON/TOML rejection;
- `..`, absolute path, ambiguous path and Zip Slip rejection;
- ZIP symlink rejection;
- archive file-count/expanded-size controls;
- serialized concurrent updates to the same project.

## Live runtime test

TitanBox v0.2.0 was started as a real Uvicorn process with the `DeployAdminPlugin` loaded (dummy Telegram token; webhook auto-registration disabled).

Verified live:

- `/healthz`: passed;
- `/readyz`: passed;
- `/admin/status` with valid bearer token: passed;
- Deploy Admin plugin binding: passed;
- wrong Telegram webhook secret: **HTTP 403** as expected.

## Webhook stress smoke test

The real `/telegram/deploy-admin` route was hit with **1,500 unique webhook updates** at concurrency **50**. The test used a non-admin Telegram user ID, so it exercised webhook secret verification, JSON parsing, dedupe, concurrency control and plugin routing without making outbound Telegram API calls.

Observed in this shared build environment:

- failures: **0**
- throughput: ~**277.7 req/s**
- p50: ~**113 ms**
- p95: ~**521 ms**
- p99: ~**819 ms**
- `titanbox_webhook_handled_total`: **1500**
- wrong-secret request: **403**
- process peak RSS after the run: ~**123 MB**

These are not Render/Railway capacity guarantees. The environment has different CPU, memory accounting and scheduling. The useful result is zero failures under the smoke load and a stable single-process control plane.

## Tooling limitation in this build sandbox

`ruff` is declared in `requirements-dev.txt` and the GitHub Actions CI runs `ruff check .` on Python 3.12 and 3.13. Ruff was not available locally in this sandbox, and outbound package installation was blocked by DNS, so a local Ruff invocation could not be completed here.

A Docker/Podman engine is also not available in this sandbox. The included GitHub Actions `docker-build` job performs a real Docker Buildx build and starts the built image, then checks `/healthz` on every push/PR.
