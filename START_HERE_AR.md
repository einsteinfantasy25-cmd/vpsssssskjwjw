# ابدأ من هنا — TitanBox v0.3.0 FINAL

هذه النسخة صُممت لإصلاح المشاكل التي ظهرت فعلياً أثناء نشر v0.2 على Render.

## أهم تغيير

على Render لا تحتاج في أول Deploy إلى إدخال `BOTS_JSON` أو `PUBLIC_BASE_URL` أو Telegram Admin ID.

`render.yaml` يجهز Deploy Admin تلقائياً، وRender سيطلب منك قيمة سرية واحدة أساسية:

```text
DEPLOY_BOT_TOKEN
```

ضع Token الحقيقي الذي حصلت عليه من BotFather.

## رفع المشروع إلى GitHub

فك ZIP وارفع **محتويات مجلد TitanBox-0.3.0-FINAL كاملة** إلى جذر repository.

الصفحة الرئيسية للـrepo يجب أن تعرض مباشرة:

```text
Dockerfile
render.yaml
requirements.txt
src/
config/
scripts/
nginx/
```

لا تجعلها بهذا الشكل:

```text
repo/
  TitanBox-0.3.0-FINAL/
    Dockerfile
    src/
```

بل بهذا الشكل:

```text
repo/
  Dockerfile
  src/
  config/
  scripts/
  nginx/
```

## Render — أول تشغيل

1. New → Blueprint.
2. اختر GitHub repo.
3. Render يقرأ `render.yaml`.
4. عندما يطلب `DEPLOY_BOT_TOKEN`، ضع Token من BotFather.
5. Apply/Deploy.

TitanBox v0.3 يقرأ رابط الخدمة تلقائياً من متغير Render الرسمي `RENDER_EXTERNAL_URL`؛ لا تستخدم `placeholder.invalid`.

## بعد نجاح Deploy

افتح رابط Render. ستشاهد Dashboard بسيطة، وليست Terminal.

افحص:

```text
/
/setup
/status
/healthz
/readyz
```

إذا `/healthz` = OK لكن `/readyz` = 503، افتح `/status`: سيخبرك بالضبط أي Bot فشل ولماذا.

## أول /start في Telegram

افتح Deploy Admin Bot واضغط:

```text
/start
```

إذا لم تضف Admin ID بعد، البوت لن يسكت. سيرسل لك شيئاً مثل:

```text
Telegram numeric ID: 123456789
Status: غير مصرح بعد
```

اذهب إلى Render → Service → Environment وأضف:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=123456789
```

ثم Save/Redeploy.

بعدها أرسل:

```text
/start
/diag
```

`/diag` يعرض Bot username، رابط Webhook الحالي، الرابط المتوقع، Pending updates وآخر خطأ Telegram.

## ملفات ومشاريع

بوت الإدارة يدعم:

```text
/projects
/use NAME
/status [NAME]
/files [NAME]
/releases [NAME]
/rollback [NAME]
/restart [NAME]
```

لرفع ZIP:

```text
/deploy mybot
```

يكتب الأمر في Caption للـZIP.

لتحديث ملف واحد:

```text
/put mybot path/to/file.py
```

مهم: رفع ZIP إلى Deploy Admin لا يعني أن TitanBox سيشغّل أي كود مجهول تلقائياً. تشغيل مشروع مستقل يحتاج ربطه بالـRunner أو تحويله إلى Ultra Mode plugin.

## مهم جداً: Render Free والملفات

Render Free يستخدم filesystem مؤقتاً. أي ملف ترفعه أثناء التشغيل يمكن أن يختفي عند restart/redeploy/spin-down.

لذلك:

- استخدم رفع الملفات على Render Free للاختبار فقط.
- الكود الدائم اجعله في GitHub.
- البيانات الدائمة اجعلها في database/object storage خارجي.
- إذا أردت إدارة ملفات دائمة من Telegram، استخدم منصة فيها Volume/Persistent Disk أو نضيف backend خارجي لاحقاً.

## فحص repository قبل Render

من terminal داخل المشروع:

```bash
python scripts/preflight_repo.py
```

إذا repo ناقص `src/` أو `config/` أو `scripts/` أو `nginx/` تحصل رسالة واضحة قبل Docker build.
