.PHONY: test lint check run

test:
	pytest -q

lint:
	ruff check .

check: lint test
	python -m compileall -q src tests examples
	bash -n scripts/entrypoint.sh scripts/smoke_test.sh tests/chaos/manual_chaos.sh

run:
	PYTHONPATH=src uvicorn titanbox.main:app --host 0.0.0.0 --port $${PORT:-10000} --workers 1
