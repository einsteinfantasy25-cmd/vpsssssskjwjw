# Deploy Admin Bot — TitanBox v0.3

## أول تشغيل على Render

`render.yaml` يضيف Deploy Admin تلقائياً. لا تحتاج كتابة `BOTS_JSON` يدوياً في أول Deploy.

Render يطلب:

```text
DEPLOY_BOT_TOKEN
```

ضع Token الحقيقي من BotFather.

TitanBox يشتق Webhook secret آمناً تلقائياً من `WEBHOOK_SECRET_KEY` الداخلي، ويكتشف رابط Render تلقائياً.

## معرفة Telegram ID بدون مواقع خارجية

أرسل:

```text
/start
```

إذا لم تكن مصرحاً، البوت يرد برقمك فقط وتعليمات التفعيل. بعد ذلك أضف داخل Render:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=123456789
```

ثم Redeploy.

## التشخيص

```text
/whoami
/diag
```

`/diag` يعرض username، Expected/Actual webhook، pending updates وآخر خطأ Telegram.

## أوامر الملفات

```text
/projects
/use mybot
/status mybot
/files mybot
/releases mybot
/rollback mybot
/restart mybot
```

رفع ZIP، Caption:

```text
/deploy mybot
```

تحديث ملف واحد، Caption:

```text
/put mybot path/to/file.py
```

أو:

```text
/use mybot
```

ثم أرسل ملفاً بلا Caption؛ إذا كان اسمه فريداً في المشروع، TitanBox يحدد المسار تلقائياً.

## ماذا يعني Deployment هنا؟

TitanBox يعمل staging + validation + release + atomic current switch. **لا ينفذ أي ZIP عشوائي تلقائياً**. إذا كان المشروع مربوطاً باسم مماثل داخل Legacy Runner، يمكن إعادة تشغيله والتحقق من استقراره. وإلا تكون العملية إدارة ملفات/نسخ فقط.

## Render Free

رفع الملفات محلياً على Render Free ليس تخزيناً دائماً. التغييرات يمكن أن تختفي عند restart/redeploy/spin-down. احتفظ بالكود الحقيقي في GitHub أو استخدم تخزيناً/Volume دائماً على منصة مناسبة.
