# TitanBox v0.3 Troubleshooting

## `/start` says I am not authorized
This is expected on first boot. The message includes your numeric Telegram ID. Put it into:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=<your number>
```

in Render Environment and redeploy.

## `/start` does not arrive at all
Open `/status` and `/readyz`. Then use Render logs. Typical states:

- `missing environment secret DEPLOY_BOT_TOKEN` → BotFather token is missing.
- webhook registration error → check token/network and `/diag` after authorization.
- bot loaded but not ready → compare expected and actual webhook.

## I don't know what the Render URL is for
Open the root URL. v0.3 renders a human-readable TitanBox dashboard. `/setup` gives next steps.

## Docker says the repository is incomplete
v0.3 uses one build-context COPY and prints the missing mandatory paths. Your GitHub root must include `src/`, `config/`, `scripts/`, `nginx/`, `Dockerfile` and `render.yaml`.

## `free -h` shows huge RAM
Host totals do not equal your container limit. TitanBox `/healthz` and `/metrics` use cgroup-aware readings.

## Uploaded files disappeared
Expected on Render Free. Its local filesystem is ephemeral. Keep durable code in Git and durable files/data outside the container.

## `/deploy` says Restarted: false
The uploaded project is versioned/validated but not connected to Legacy Runner. Uploading arbitrary code does not automatically execute it. Configure Runner intentionally or adapt the bot to Ultra Mode.

## AppRunner circuit opened
The child application crashed too many times inside its restart window. Fix the underlying error, then start/restart it again.

## Out of memory
Disable terminal, avoid duplicated bot processes, reduce concurrency/caches, stream files and move heavy AI/PDF/audio work off-box.
