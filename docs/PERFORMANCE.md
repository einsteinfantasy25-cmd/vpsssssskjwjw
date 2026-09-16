# Performance design

TitanBox optimizes for small free-tier containers rather than pretending to create more RAM than the platform grants.

- One Uvicorn worker by default: avoids duplicating the interpreter and imported libraries.
- Async I/O: HTTP requests and Telegram calls share one event loop.
- Shared `httpx.AsyncClient`: bounded connection pool, keep-alive reuse.
- Bounded dedupe cache: 2048 update IDs per bot, not an unbounded dictionary.
- No local database, no GUI, no Chromium, no VNC.
- No in-memory log ring; child logs stream to platform logs.
- Heavy jobs should be queued externally. Do not run Whisper/FFmpeg/LLMs inside the webhook handler on 512 MB free instances.
- Read `/metrics` and `/healthz` to see cgroup memory instead of believing host-level `free -h` output.

## Recommended budget for 512 MB platforms

- TitanBox control plane + Ultra Mode bots: keep comfortably below the platform ceiling.
- Legacy bot processes: add one at a time and observe cgroup memory.
- Reserve at least 25-30% headroom for Python bursts, TLS buffers, deployment variance and platform overhead.
- If a bot needs large PDF/audio work, send the object to external storage/AI and return a job ID instead of loading the whole file into RAM.
