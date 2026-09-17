# TitanBox v1 test strategy

Local gates:

```bash
python scripts/preflight_repo.py
python scripts/secret_scan.py
ruff check .
python -m compileall -q src tests scripts examples
bash -n scripts/entrypoint.sh scripts/smoke_test.sh tests/chaos/manual_chaos.sh
pytest -q
```

CI additionally runs dependency auditing, CodeQL, Docker build and live `/healthz` smoke test.

Failure classes include settings/secrets, webhook authentication, retry/dedupe, request limits, rate/concurrency/circuit containment, TOTP/admin isolation, audit tamper detection, malicious ZIP/path cases, release integrity/rollback, S3 candidate->active protocol, HMAC metadata tamper detection, required-backend failure behavior, persistent admin job enqueue/resume semantics, runner crash loops and committed-secret scanning.
