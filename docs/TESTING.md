# Test strategy

Run locally:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
python -m compileall -q src tests
bash -n scripts/entrypoint.sh scripts/smoke_test.sh
```

Load test after starting TitanBox:

```bash
docker run --rm -i -e BASE_URL=http://host.docker.internal:10000 grafana/k6 run - < tests/load/k6.js
```

## Failure scenarios covered

- invalid BOTS_JSON
- terminal enabled without safe credentials
- hidden admin API without token
- unauthorized admin API request
- wrong Telegram webhook secret
- duplicate Telegram update IDs
- legacy child clean exit
- child crash loop and circuit breaker
- graceful close

## Manual chaos checklist

- kill a legacy child and verify restart/backoff
- force child crash repeatedly and verify circuit opens
- stop the container during active requests and verify clean SIGTERM
- redeploy and confirm no dependency on local persistent state
- enable terminal, confirm authentication, then disable it and confirm `/terminal/` disappears
- load test `/healthz` and observe p95 latency and cgroup memory
