# TitanBox v0.3.0

TitanBox is a lightweight Telegram bot runtime/control plane designed for tiny PaaS containers such as Render/Railway without pretending that a container is a magically larger VPS.

For the Arabic deployment walkthrough, start with **`START_HERE_AR.md`**.

## v0.3 highlights

- Render URL auto-detection (`RENDER_EXTERNAL_URL` / `RENDER_EXTERNAL_HOSTNAME`)
- one-secret first deploy on Render (`DEPLOY_BOT_TOKEN`)
- automatic webhook registration and verification
- safe derived Telegram webhook secret
- `/start` discovery mode that reports your numeric Telegram ID without granting admin access
- `/diag`, `/setup`, `/status`, improved `/readyz`
- per-bot startup error isolation
- friendly incomplete-repository Docker failure
- existing safe deployment/rollback, resource limits, Web Terminal-off-by-default and multi-bot engine

## Important platform truth

Render Free has an ephemeral filesystem. Uploaded runtime files are not durable across restart/redeploy/spin-down. Keep durable code in Git and durable data in external storage/databases.
