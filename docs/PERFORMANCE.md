# TitanBox v1 performance / resource containment

- one Uvicorn worker by default
- async HTTP/Telegram I/O and shared connection pools
- global/per-bot concurrency limits
- token-bucket rate limiting
- failure circuit breaker
- bounded update dedupe
- streamed webhook request size cap
- cgroup-aware memory pressure backpressure
- streamed Telegram downloads and bounded ZIP expansion
- lazy import of boto3/asyncpg: disabled backends do not pay their normal startup path
- external S3/PostgreSQL checks are not part of `/healthz`
- bot loads before background infrastructure validation to reduce cold-start critical path

Heavy transcription/LLM/OCR/video/PDF tasks must not run inside the Deploy Admin webhook handler. Put them in isolated bot/worker services with bounded queues.
