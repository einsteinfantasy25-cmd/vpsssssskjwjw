# Render deployment — TitanBox v1.0.0

For an existing service use `UPGRADE_EXISTING_RENDER_AR.md`. For a new service:

1. Put repository contents at GitHub repo root.
2. Render -> New -> Blueprint -> select repo.
3. Supply `DEPLOY_BOT_TOKEN` when requested.
4. Deploy.
5. `/start` gives your Telegram numeric ID if admin list is not configured.
6. Add `DEPLOY_ADMIN_TELEGRAM_IDS` and redeploy.
7. `/diag`, `/security`, `/infra`.

The Blueprint keeps S3/PostgreSQL optional on the first deploy. Add those provider credentials manually later; see `FINAL_SETUP_AR.md`.

`RELEASE_SIGNING_KEY` is generated as a platform secret. `autoDeployTrigger: checksPass` waits for linked checks before automatic deployment.

This Render service is a control plane only. Do not add student/public bot plugins to it.
