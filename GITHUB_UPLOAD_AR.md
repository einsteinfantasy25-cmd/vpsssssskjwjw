# شلون ترفع v0.4 إلى GitHub — للمبتدئ

الحزمة كاملة وليست ملف Python واحد لأن الإصلاحات موزعة على Docker/Render/runtime/security/tests/CI.

## مهم

بعد فك ZIP ستجد مجلد `TitanBox-0.4.0-HARDENED`. ارفع **المحتويات اللي داخله** إلى جذر repository الحالي.

يجب أن تشوف في الصفحة الرئيسية لـGitHub مباشرة:

```text
Dockerfile
render.yaml
requirements.txt
src/
scripts/
config/
.github/
```

لا تجعلها:

```text
repo/TitanBox-0.4.0-HARDENED/Dockerfile
```

خذ Backup/Branch من النسخة الحالية أولاً، ثم استبدل الملفات. لا تضع Bot Token داخل أي ملف. الـToken يبقى في Render Environment.

بعد Push انتظر GitHub Actions؛ `render.yaml` مضبوط على `checksPass` حتى لا ينشر commit فاشل تلقائياً. بعد نجاح Render افتح `/status` ثم أرسل `/diag`, `/security`, `/system` في Telegram.
