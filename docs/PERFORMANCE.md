# TitanBox v0.4 performance and resource containment

TitanBox optimizes for small containers without pretending to create more CPU/RAM than the host grants.

- One Uvicorn worker by default avoids duplicating Python/library memory.
- Async I/O and a shared `httpx.AsyncClient` reuse connections.
- Global and per-bot semaphores cap concurrent webhook work.
- Per-bot token buckets contain noisy bots.
- Handler timeouts and a failure circuit breaker stop repeated failures from consuming the whole runtime.
- Update dedupe is bounded; an in-flight duplicate receives a retry response instead of a premature success acknowledgement.
- Webhook bodies are streamed under `WEBHOOK_MAX_BODY_BYTES`.
- Memory pressure uses cgroup-aware readings.
- Uploads/downloads are streamed; archive expansion is limited by count and extracted bytes.
- Heavy AI/audio/PDF work should leave the webhook service and run externally/through a queue.

For a 512 MiB-class environment, keep meaningful headroom for Python bursts, TLS/network buffers, deploy variance, and platform overhead. Do not size capacity from host-level `free -h`; use container/cgroup metrics.
