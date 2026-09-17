# TitanBox v0.4 test strategy

Run locally:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/preflight_repo.py
python scripts/secret_scan.py
ruff check .
python -m compileall -q src tests examples
bash -n scripts/entrypoint.sh scripts/smoke_test.sh tests/chaos/manual_chaos.sh
pytest -q
```

CI additionally performs dependency auditing, CodeQL analysis, a real Docker build, and a `/healthz` smoke test.

Covered failure/security classes include malformed configuration, missing secrets, wrong webhook secret, token leakage prevention, webhook-body limits, rate/concurrency containment, failure circuits, duplicate/update retry semantics, Admin API authentication, private-chat admin behavior, optional TOTP, audit-chain tamper detection, ZIP traversal/symlink/duplicate-path/Unicode attacks, syntax/config validation, release integrity/tamper detection, independent rollback copies, concurrent deploy serialization, runner crash loops, and committed-secret rejection.

Manual chaos checks should also test process/container termination, repeated child crashes, redeploy with no local persistence assumptions, external DB/storage outages, and recovery after webhook replacement.
