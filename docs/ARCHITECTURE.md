# TitanBox architecture

TitanBox is intentionally not a fake VPS. It is a lightweight Linux container runtime designed for PaaS platforms.

## Fast path: Ultra Mode

Telegram -> HTTPS webhook -> one FastAPI process -> shared HTTP client -> plugin routers -> external DB / AI / object storage.

Three or twenty low-traffic bots can share one process. Each bot has a separate token and Telegram webhook secret, but shares the event loop, HTTP connection pool and Python libraries.

## Compatibility path: Legacy Runner

Existing bot scripts can run as child processes from `config/apps.toml`. The runner provides:

- graceful termination and process-group cleanup
- exponential backoff with jitter
- crash-loop circuit breaker
- bounded file descriptors
- reduced scheduling priority (`nice`)
- secret allow-listing with `env_passthrough`
- stdout/stderr streaming without an in-memory log cache

Use this only when adapting a bot to Ultra Mode is impractical, because every Python child has its own interpreter and library memory.

## Optional browser terminal

`ENABLE_TERMINAL=true` activates ttyd behind nginx at `/terminal/`. It is off by default. No SSH daemon or desktop environment is installed.

## Persistence

Treat the local filesystem as disposable. On Render Free it is explicitly ephemeral. Store real data in an external database/object store. Railway volumes can persist data, but TitanBox itself does not require a volume.
