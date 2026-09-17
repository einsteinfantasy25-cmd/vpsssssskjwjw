# ابدأ من هنا — TitanBox v0.4.0 HARDENED

هذه النسخة هي تحديث أمني/احترافي للـDeploy Admin الذي عندك الآن. الهدف أن يبقى **بوت الإدارة Control Plane وحده** في هذه الخدمة، ولا نضع داخله بوتات الطلاب مستقبلاً.

## 1) ماذا ترفع إلى GitHub؟

فك ملف ZIP وارفع **محتويات مجلد `TitanBox-0.4.0-HARDENED` نفسها** إلى جذر Repository.

الصحيح:

```text
repo/
  Dockerfile
  render.yaml
  requirements.txt
  src/
  config/
  scripts/
  tests/
  .github/
```

الخطأ:

```text
repo/
  TitanBox-0.4.0-HARDENED/
    Dockerfile
    src/
```

## 2) إذا Render عندك شغال أصلاً

لا تحذف الخدمة ولا تنشئ Bot جديد للإدارة.

1. استبدل ملفات GitHub بالنسخة الجديدة.
2. Render → Blueprint/Service → Sync أو Manual Deploy → latest commit.
3. لا تغيّر `DEPLOY_BOT_TOKEN` الحالي.
4. لا تغيّر `DEPLOY_ADMIN_TELEGRAM_IDS` الحالي.
5. بعد نجاح النشر افتح:

```text
https://YOUR-SERVICE.onrender.com/status
```

يجب أن ترى:

```text
"version": "0.4.0"
"configured_bots": 1
"loaded_bots": 1
"bots_ready": true
```

تفاصيل البوتات نفسها مخفية من الصفحة العامة افتراضياً وهذا مقصود أمنياً.

## 3) افحص من Telegram

أرسل لبوت الإدارة:

```text
/start
/diag
/security
/system
```

`/security` هو أهم أمر بعد التحديث.

## 4) العزل الذي فعّلناه

Render Blueprint الجديد يضع:

```text
CONTROL_PLANE_ONLY=true
MAX_BOTS_PER_RUNTIME=1
```

هذا يمنعنا مستقبلاً من إضافة Medical Bot بالغلط إلى نفس Process مال Deploy Admin.

**بوت الإدارة يبقى وحده.**

البوت الطبي القوي لاحقاً يأخذ Service/Container مستقل.

## 5) 2FA — اختياري أول يوم، موصى به قبل الإنتاج

النسخة لا تجبرك عليه مباشرة حتى لا ينقفل عليك البوت أثناء الترقية.

عندما تكون جاهزاً:

```text
DEPLOY_REQUIRE_2FA=true
DEPLOY_TOTP_SECRET=<BASE32 SECRET>
```

ثم الأوامر الحساسة تحتاج:

```text
/auth 123456
```

وتبقى الجلسة مفتوحة افتراضياً 5 دقائق ثم تنقفل.

لا ترسل TOTP secret إلى Telegram ولا تضعه في GitHub.

راجع `docs/2FA_AR.md`.

## 6) التخزين

رفع ZIP أو ملف من Telegram ما زال يستخدم مساحة Render المحلية أثناء التشغيل. Render Free filesystem مؤقت.

لذلك:

- GitHub = مصدر الكود الدائم.
- External DB = بيانات المستخدمين الدائمة.
- Object Storage = PDF/audio/images/backups الدائمة.
- Render local = ملفات مؤقتة فقط.

هذا ليس Bug في TitanBox؛ هو حد في منصة الاستضافة.

## 7) لا تستخدم حيلة داخلية لمنع Render من النوم

Outbound ping من TitanBox إلى Telegram لا يمنع نوم Render. التصميم الصحيح يجعل الخدمة تستيقظ وتعيد Webhook وتسترجع بياناتها من المصادر الدائمة بدون فقدان شيء.

## 8) إذا صار خطأ بعد الترقية

افتح:

```text
/healthz
/readyz
/status
```

ومن Telegram:

```text
/diag
/security
```

ثم Render Logs. لا ترسل أي Token في صورة أو رسالة.
