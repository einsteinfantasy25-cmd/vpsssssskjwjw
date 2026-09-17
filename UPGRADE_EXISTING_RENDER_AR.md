# ترقية Render الحالي من TitanBox v0.2 إلى v0.3

هذا الملف لك إذا **الخدمة موجودة أصلاً على Render** ولا تريد إنشاء Service جديدة.

## 1) GitHub

استبدل محتويات الـrepo القديم بمحتويات v0.3 كاملة. تأكد أن جذر repo يظهر:

```text
Dockerfile
render.yaml
requirements.txt
src/
config/
scripts/
nginx/
```

## 2) Render Blueprint

اعمل Manual Sync للـBlueprint أو انتظر Auto Sync بعد commit.

`render.yaml` الجديد سيصحح تلقائياً:

```text
BOTS_JSON = Deploy Admin descriptor
AUTO_REGISTER_WEBHOOKS = true
ENABLE_TERMINAL = false
ENABLE_RUNNER = false
```

## 3) مهم: DEPLOY_BOT_TOKEN

لأن الخدمة قديمة، لا تعتمد على أن Render سيطلب منك `sync: false` من جديد.

اذهب يدوياً:

```text
Render → titanbox service → Environment
```

وتأكد أن عندك:

```text
DEPLOY_BOT_TOKEN=<BotFather token الحقيقي>
```

إذا غير موجود، أضفه ثم Save.

## 4) القيم القديمة

إذا بقي عندك:

```text
PUBLIC_BASE_URL=https://placeholder.invalid
DEPLOY_ADMIN_TELEGRAM_IDS=0
DEPLOY_BOT_SECRET=...
```

v0.3 لن يعتمد عليها بالشكل القديم:

- placeholder القديم يتم تجاهله ويُستخدم رابط Render الحقيقي تلقائياً.
- Admin ID = 0 يعتبر غير مضبوط.
- `DEPLOY_BOT_SECRET` القديم غير مطلوب إذا كنت تستخدم الـBlueprint النهائي؛ TitanBox يشتق secret مناسباً من `WEBHOOK_SECRET_KEY`.

يمكن حذف القيم القديمة بعد نجاح الترقية لتقليل الالتباس.

## 5) Deploy

شغّل:

```text
Manual Deploy → Deploy latest commit
```

ثم افتح رابط Render الرئيسي.

يجب أن تشاهد Dashboard TitanBox v0.3.

## 6) افحص

افتح:

```text
/healthz
/status
/readyz
```

المطلوب:

- `/healthz` → 200.
- `/status` → configured_bots=1 وبدون token leak.
- `/readyz` → 200 إذا Telegram webhook نجح.

إذا `/readyz` = 503، السبب مكتوب داخل `/status` بدلاً من التخمين.

## 7) Telegram Admin ID

أرسل للبوت:

```text
/start
```

إذا Admin ID غير مضبوط، سيعطيك رقمك بنفسه.

ضع داخل Render:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=<الرقم>
```

ثم Save/Redeploy.

بعدها:

```text
/start
/diag
```

إذا `/diag` يبين Expected webhook = Telegram webhook، الربط اكتمل.
