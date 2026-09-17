# TitanBox v0.3.0 FINAL — ملخص النسخة

هذه هي حزمة الإصلاح الشاملة بعد المشاكل الفعلية التي ظهرت على Render.

## المطلوب منك بعد رفعها

1. ارفع **كل** محتويات هذا المجلد إلى GitHub root.
2. Render → New Blueprint → اختر repo.
3. أدخل `DEPLOY_BOT_TOKEN` فقط عندما يطلبه Render.
4. بعد Live، افتح البوت وأرسل `/start`.
5. خذ Telegram numeric ID الذي يرسله البوت.
6. Render → Environment → أضف `DEPLOY_ADMIN_TELEGRAM_IDS=<ID>`.
7. Redeploy.
8. أرسل `/start` ثم `/diag`.

## لا تضف هذه القيم القديمة

لا تستخدم:

```text
PUBLIC_BASE_URL=https://placeholder.invalid
DEPLOY_ADMIN_TELEGRAM_IDS=0
BOTS_JSON=[]
AUTO_REGISTER_WEBHOOKS=false
```

النسخة الجديدة جهزت هذا المسار تلقائياً.

## قاعدة تشخيص سريعة

- `/healthz` 200 = TitanBox نفسه حي.
- `/readyz` 200 = البوتات المحملة جاهزة أيضاً.
- `/readyz` 503 = افتح `/status` لتقرأ السبب الدقيق.
- `/diag` من Telegram = فحص مباشر لـBotFather token/Webhook/Pending updates.

## حقيقة Render Free

لا يوجد إصلاح برمجي يحول filesystem المؤقت إلى قرص دائم. الملفات التي ترفعها أثناء التشغيل قد تختفي بعد restart/redeploy/spin-down. استعمل GitHub للكود الدائم، وتخزيناً خارجياً للملفات الدائمة.
