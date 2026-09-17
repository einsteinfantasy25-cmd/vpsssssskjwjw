# TitanBox v1.0.0 FINAL — Quick Start

1. فك ZIP وارفع محتويات `TitanBox-1.0.0-FINAL` إلى **جذر** GitHub repo الحالي.
2. لا تحذف `DEPLOY_BOT_TOKEN` أو `DEPLOY_ADMIN_TELEGRAM_IDS` من Render.
3. GitHub Actions لازم تنجح، بعدها Render Deploy.
4. افتح `/status`: نريد `version=1.0.0`, `loaded_bots=1`, `bots_ready=true`.
5. Telegram: `/diag` ثم `/security` ثم `/infra` ثم `/setup`.
6. فعّل S3 وPostgreSQL حسب `FINAL_SETUP_AR.md` عندما تكون جاهزاً للـPersistence.
7. فعّل 2FA قبل الإدارة الجدية.

مهم: `/wakez` يساعد على Wake-on-request، لكنه ليس keepalive. Render Free سيبقى خاضعاً لسياسة النوم الخاصة بالمنصة.
