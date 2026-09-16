# TitanBox

**TitanBox** is an ultra-light Linux/PaaS runtime built for the exact use case of running a few Telegram bots on small free-tier containers without wasting RAM on a desktop, VNC, Chromium, SSH daemons, or duplicated bot engines.

It is intentionally **not** a quota bypass and it cannot turn 512 MB into 32 GB. Its goal is the opposite: make 512 MB behave intelligently by removing unnecessary work.

## What is inside

- Ultra Mode: multiple Telegram bots in **one Python process** with one event loop and one HTTP pool.
- Telegram webhook secret verification and bounded update deduplication.
- Optional Legacy Runner for existing independent bot scripts.
- Crash recovery, exponential backoff, jitter, and crash-loop circuit breaker.
- `/healthz`, `/readyz`, `/metrics` with Linux cgroup memory reporting.
- Protected admin API for status/start/stop/restart.
- Optional writable browser terminal with `ttyd`, off by default.
- Non-root container, no SSH/VNC/desktop/Chrome.
- Render Blueprint, Railway config, Docker Compose, load test and automated tests.
- Telegram Deploy Admin: ZIP deployment, safe single-file updates, release history, restart verification and rollback.

## Fast start

```bash
cp .env.example .env
# edit .env; keep ENABLE_TERMINAL=false initially
docker compose up --build
curl http://localhost:10000/healthz
```

## Ultra Mode: three bots, one engine

Create three Telegram bots and three webhook secrets, then set:

```env
BOTS_JSON=[
  {"name":"anatomy","token_env":"ANATOMY_TOKEN","secret_env":"ANATOMY_SECRET","plugin":"mybots.anatomy:Plugin"},
  {"name":"physiology","token_env":"PHYSIO_TOKEN","secret_env":"PHYSIO_SECRET","plugin":"mybots.physiology:Plugin"},
  {"name":"medstudy","token_env":"MED_TOKEN","secret_env":"MED_SECRET","plugin":"mybots.medstudy:Plugin"}
]
ANATOMY_TOKEN=...
ANATOMY_SECRET=...
PHYSIO_TOKEN=...
PHYSIO_SECRET=...
MED_TOKEN=...
MED_SECRET=...
PUBLIC_BASE_URL=https://your-service.example
AUTO_REGISTER_WEBHOOKS=true
```

Each plugin is a small class:

```python
class Plugin:
    async def handle(self, update, bot):
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if chat_id:
            await bot.send_message(chat_id, "Hello from my bot")
```

All bots share TitanBox's event loop and connection pool instead of launching three copies of the whole framework.

## Admin API

Set `ADMIN_TOKEN` to a long random secret.

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://host/admin/status
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" https://host/admin/apps/old-bot/restart
```

## Browser terminal

Only when needed:

```env
ENABLE_TERMINAL=true
TERMINAL_USER=your-user
TERMINAL_PASSWORD=a-very-long-unique-password
```

Then open `/terminal/`. Disable it again when finished.

## Read first

- `docs/ARCHITECTURE.md`
- `docs/PERFORMANCE.md`
- `docs/SECURITY.md`
- `docs/DEPLOY_RENDER.md`
- `docs/DEPLOY_RAILWAY.md`
- `docs/TESTING.md`
- `docs/TEST_REPORT.md`
- `docs/DEPLOY_BOT_AR.md`
- `docs/REFERENCES.md`

## Platform reality

Render Free currently sleeps after 15 minutes without inbound traffic and uses an ephemeral filesystem. Railway offers Docker deployment and optional volumes with plan-specific limits. TitanBox is designed around those constraints rather than pretending they do not exist.

## Doctor

Inside the container, run `python /app/scripts/doctor.py` to validate settings, cgroup memory visibility, writable temporary/workspace paths, and Telegram DNS.
