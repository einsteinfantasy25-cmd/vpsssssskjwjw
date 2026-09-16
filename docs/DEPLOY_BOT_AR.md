# بوت الإدارة والنشر من Telegram

هذه الميزة تسمح لك بإدارة ملفات مشاريعك من Telegram بدون فتح Terminal.

## ماذا يفعل؟

- يستقبل مشروع ZIP وينشره كـRelease جديدة.
- يستقبل ملفاً واحداً ويضيفه أو يحدّثه داخل مشروع موجود.
- إذا أرسلت ملفاً بدون مسار وكان اسم الملف موجوداً بمكان واحد فقط، يكتشف مكانه ويحدثه تلقائياً.
- يفحص مسارات ZIP ضد Zip Slip و`..` والمسارات المطلقة والـsymlinks.
- يضع حدوداً لعدد الملفات وحجم ZIP بعد الفك.
- يفحص Syntax لملفات Python ويقرأ JSON/TOML قبل اعتماد الـRelease.
- كل تحديث يصبح Release مستقلة؛ التبديل إلى `current` يتم بشكل atomic.
- يدعم Rollback للنسخة السابقة.
- إذا كان اسم المشروع مربوطاً بـLegacy Runner، يعيد تشغيله بعد التحديث ويتأكد أنه بقي مستقراً. إذا فشل، يعيد النسخة السابقة تلقائياً.
- عمليات النشر تدخل Queue داخلية ولا تحبس Telegram webhook.

## 1) أنشئ بوت إدارة من BotFather

خذ Token وحطه كـEnvironment Variable، مثال:

```text
DEPLOY_BOT_TOKEN=123456:...
DEPLOY_BOT_SECRET=random_AZaz09_-_secret
```

لا تكتب Token داخل GitHub.

## 2) أضف Deploy Bot إلى BOTS_JSON

مثال إذا عندك Deploy Bot فقط:

```json
[{"name":"deploy-admin","token_env":"DEPLOY_BOT_TOKEN","secret_env":"DEPLOY_BOT_SECRET","plugin":"titanbox.plugins.deploy_admin:DeployAdminPlugin"}]
```

وممكن يكون ضمن نفس array مع بوتاتك الأخرى.

## 3) اسمح فقط لحسابك

```text
DEPLOY_ADMIN_TELEGRAM_IDS=123456789
```

ممكن أكثر من Admin بفاصلة:

```text
DEPLOY_ADMIN_TELEGRAM_IDS=123456789,987654321
```

إذا Plugin الإدارة موجود وماكو Admin IDs، TitanBox يرفض الإقلاع بدلاً من تشغيل Deploy Bot مفتوح للناس.

## 4) الأوامر

```text
/projects
/use mybot
/status mybot
/files mybot
/releases mybot
/restart mybot
/rollback mybot
```

### نشر مشروع كامل

ارسل `mybot.zip` كـDocument واكتب بالـCaption:

```text
/deploy mybot
```

إذا ZIP يحتوي فولدر رئيسي واحد فقط، TitanBox يزيل هذه الطبقة تلقائياً.

### تحديث ملف واحد

ارسل الملف نفسه كـDocument، مثلاً `main.py`، واكتب:

```text
/put mybot main.py
```

أو ملف داخل مجلد:

```text
/put mybot assets/logo.png
```

### الوضع الذكي

أولاً:

```text
/use mybot
```

بعدها ارسل `main.py` بدون Caption. إذا يوجد `main.py` واحد فقط داخل المشروع، TitanBox يعرف مكانه ويعمل Update آمن تلقائياً. إذا الاسم موجود بأكثر من مكان، يرفض التخمين ويعرض لك المسارات حتى تختار الصحيح.

## 5) ربط التحديث بالتشغيل

إذا تريد بعد كل Update البوت يعاد تشغيله ويتفحص، لازم يكون اسم المشروع نفسه اسم App في `config/apps.toml`.

مثال:

```toml
[[apps]]
name = "mybot"
enabled = true
cwd = "/workspace/titanbox-data/projects/mybot/current"
command = ["python", "-u", "main.py"]
restart = "always"
max_restarts = 8
restart_window_seconds = 600
backoff_base_seconds = 1.0
backoff_max_seconds = 60.0
max_open_files = 512
nice = 5
env_passthrough = ["MYBOT_TOKEN", "DATABASE_URL"]
```

وفعّل:

```text
ENABLE_RUNNER=true
```

النتيجة:

```text
Telegram file
  -> temp download (streaming)
  -> staging release
  -> static validation
  -> atomic current swap
  -> restart mybot
  -> stability check
  -> success
```

إذا فشل التشغيل:

```text
new release fails
  -> restore previous current
  -> restart previous release
  -> report failure
```

## حدود مهمة

- الحد الافتراضي للملف في TitanBox هو `19,000,000` bytes ويمكن تغييره بـ`DEPLOY_MAX_UPLOAD_BYTES`، لكن حد Telegram Bot API نفسه يعتمد على طريقة تشغيل Telegram API عندك.
- لا يتم تشغيل أوامر عشوائية من ZIP أثناء مرحلة الفحص؛ الفحص Static حتى لا يتحول مجرد Upload إلى تنفيذ قبل اعتماد النسخة.
- Dependencies الخاصة بالـPython/Node يفضل تكون ضمن صورة Docker أو بيئة معزولة؛ هذه النسخة تركز على Deploy/Update آمن وخفيف.
- على منصة ذات filesystem مؤقت مثل بعض الخطط المجانية، Releases المحلية قد تضيع عند إعادة إنشاء الـcontainer. للاستمرارية استخدم Volume/Persistent Disk أو VPS حقيقي. لا تعتبر التخزين المحلي Backup دائم.
