# ترقية Render الحالي إلى TitanBox v1.0.0 FINAL

## ما يبقى مثل ما هو

لا تغيّر:

```text
DEPLOY_BOT_TOKEN
DEPLOY_ADMIN_TELEGRAM_IDS
```

## الخطوات

1. Backup/Branch للـrepo الحالي.
2. استبدل ملفات GitHub بمحتويات v1 كاملة.
3. Commit + Push.
4. انتظر GitHub Actions.
5. Render -> Sync Blueprint إذا تستخدم Blueprint، ثم Deploy latest commit.
6. `/status` -> `version=1.0.0`, `loaded_bots=1`, `bots_ready=true`.
7. Telegram -> `/diag`, `/security`, `/infra`, `/setup`.

## Secrets الجديدة

`render.yaml` يولد `RELEASE_SIGNING_KEY` مع أسرار Admin/Webhook/Audit. إذا خدمة قديمة ما أخذته بعد Blueprint Sync، أضف Secret عشوائي >=32 chars يدوياً.

S3 وPostgreSQL **لا يتم طلب مفاتيحهم أثناء أول Upgrade** حتى ما تتعطل عليك الخدمة. تضيفهم يدوياً لاحقاً حسب `FINAL_SETUP_AR.md`.

## Safe adaptive defaults

- إذا تضيف `STORAGE_BACKEND=s3` وما تضيف `DURABILITY_REQUIRED`, يصبح Required تلقائياً.
- إذا تضيف `POSTGRES_DSN` وما تضيف `DATABASE_REQUIRED`, تصبح DB Required تلقائياً.

هذا Fail-closed افتراضياً بعد ما تقرر تشغيل الـPersistence.

## إذا فشل التحديث

إذا Build/CI فشل، لا تتجاوز الفحوصات عشوائياً. ارجع آخر commit ناجح أو أصلح الخطأ. إذا Container اشتغل والبوت مو Ready، افحص `/readyz`, `/status`, Render Logs وTelegram `/diag`.
