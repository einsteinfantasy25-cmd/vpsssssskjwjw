# Render deployment — TitanBox v0.4

## Existing v0.3 service

Use `UPGRADE_EXISTING_RENDER_AR.md`. Keep the current BotFather token and Telegram admin ID. Replace the repository contents, sync the Blueprint, and deploy the latest commit.

## New service

1. Put this repository at the GitHub repository root.
2. Render → New → Blueprint → choose the repository.
3. Supply `DEPLOY_BOT_TOKEN` when requested.
4. Deploy.
5. Send `/start` to Deploy Admin; if no admin ID is configured, the bot returns your numeric Telegram ID without granting administration.
6. Add that number to `DEPLOY_ADMIN_TELEGRAM_IDS` and redeploy.

`render.yaml` uses `autoDeployTrigger: checksPass`, so Git-based automatic deployment waits for linked CI checks to pass.

The service is hardened as a **control plane only** with `CONTROL_PLANE_ONLY=true` and `MAX_BOTS_PER_RUNTIME=1`. Public/student bots should be separate services for hard isolation.

Render Free local files are ephemeral. `/deploy` on this service is useful for controlled testing/version management, but durable production code belongs in Git and durable data/files outside local runtime storage.
