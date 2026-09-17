# Deploy TitanBox v0.3 on Render

## Recommended path

1. Upload the **complete repository root** to GitHub.
2. Render → New → Blueprint.
3. Select the repository.
4. Enter only the prompted secret `DEPLOY_BOT_TOKEN` from BotFather.
5. Deploy.

`render.yaml` already configures the Deploy Admin descriptor, `AUTO_REGISTER_WEBHOOKS=true`, resource limits and safe generated secrets.

## Public URL

Do not create a fake placeholder URL. TitanBox v0.3 resolves the Render URL from the platform-provided `RENDER_EXTERNAL_URL` / `RENDER_EXTERNAL_HOSTNAME` variables.

## Admin authorization bootstrap

The first `/start` from an unauthorized Telegram account returns that account's numeric Telegram ID and performs no admin action. Add the returned value in Render:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=123456789
```

Save/redeploy, then use `/start` and `/diag` again.

## Diagnostics

Browser:

```text
/
/setup
/status
/healthz
/readyz
```

Telegram admin:

```text
/whoami
/diag
```

## Render Free reality

- Free web services can spin down after idle periods.
- Runtime filesystem changes are ephemeral and can disappear on restart/redeploy/spin-down.
- Free web services cannot attach a persistent disk.
- The browser terminal is an optional shell inside the application container, not a real VPS SSH service.

Use Git/external databases/object storage for anything that must persist.
