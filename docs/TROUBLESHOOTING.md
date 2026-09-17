# TitanBox v0.4 troubleshooting

## `/start` لا يرد

Open `/status`. If `loaded_bots=0`, inspect the hidden details in Render logs. A common error is missing `DEPLOY_BOT_TOKEN`. If the bot is loaded but not ready, use `/diag` once Telegram replies and compare expected/actual webhook.

## `/status` لا يعرض تفاصيل البوت

Expected. v0.4 hides public bot details by default. Use Telegram `/diag`, `/security`, Render logs, or temporarily set `PUBLIC_STATUS_DETAILS=true` only when you understand the exposure.

## أمر حساس يقول `/auth 123456`

2FA is enabled. Enter the current code from your authenticator with `/auth CODE`, then repeat the command. `/lock` closes the session immediately.

## `/security` يقول Audit غير متاحة/غير سليمة

Check `AUDIT_HMAC_KEY`, local write permissions, and Render logs. On Render Free the local audit file is ephemeral; platform logs are the secondary copy. For durable audit history, export logs/storage externally.

## ZIP مرفوض

Do not bypass the validator. Fix the reported issue: unsafe path, duplicate normalized path, symlink, archive limits, invisible Unicode, malformed Python/JSON/TOML, or reserved manifest path.

## Rollback مرفوض بسبب integrity

The stored release changed after validation. Do not force it active. Deploy a known-good Git/release artifact instead.

## ملفات `/deploy` اختفت

Expected on Render Free after restart/redeploy/spin-down. Local filesystem is not durable. Keep durable code in Git and persistent data/files in external DB/object storage.

## `CONTROL_PLANE_ONLY` يمنع إضافة Bot جديد

Intentional. This service is Deploy Admin/control plane only. Create the student/public bot in a separate service/container for strong isolation.

## Render deployment لا يبدأ بعد push

v0.4 uses `autoDeployTrigger: checksPass`. Open GitHub Actions. Fix failing CI/security checks first; do not bypass them unless you intentionally switch to a manual emergency deployment.

## Out of memory / slow runtime

Use `/system`; reduce concurrency; keep terminal/runner off if unused; stream files; move AI/PDF/audio work out of the webhook process; separate public bots into independent services.
