# TitanBox — تشغيل سريع بالعربي

هذا المشروع مو VPS حقيقي ولا يحاول يتجاوز حدود Render/Railway. هو **Linux container ذكي وخفيف** يخليك تستغل الموارد المجانية بأقصى كفاءة لتشغيل بوتات Telegram.

## أسرع طريقة على Render

1. ارفع مجلد `TitanBox` كامل إلى GitHub.
2. افتح Render واختر Blueprint أو Web Service من الـGitHub repo.
3. Render راح يقرأ `render.yaml` و`Dockerfile`.
4. أضف المتغيرات السرية من Dashboard، لا تكتبها داخل GitHub.
5. حط رابط Render في `PUBLIC_BASE_URL`.
6. بعد التأكد من الرابط خلي `AUTO_REGISTER_WEBHOOKS=true` وسوِّ Deploy.

## مثال 3 بوتات داخل Process واحد

ضع `BOTS_JSON` كسطر JSON واحد:

```json
[{"name":"anatomy","token_env":"ANATOMY_TOKEN","secret_env":"ANATOMY_SECRET","plugin":"titanbox.plugins.default:DefaultPlugin"},{"name":"physiology","token_env":"PHYSIO_TOKEN","secret_env":"PHYSIO_SECRET","plugin":"titanbox.plugins.default:DefaultPlugin"},{"name":"medstudy","token_env":"MED_TOKEN","secret_env":"MED_SECRET","plugin":"titanbox.plugins.default:DefaultPlugin"}]
```

ثم أضف كل متغير بشكل منفصل:

```text
ANATOMY_TOKEN=...
ANATOMY_SECRET=...
PHYSIO_TOKEN=...
PHYSIO_SECRET=...
MED_TOKEN=...
MED_SECRET=...
```

الـSecret الخاص بالWebhook استخدم به فقط حروف/أرقام و `_` و `-`.

## الـWeb Terminal

افتراضياً مطفي حتى نوفر RAM ونقلل الخطر.

إذا احتجته مؤقتاً:

```text
ENABLE_TERMINAL=true
TERMINAL_USER=admin
TERMINAL_PASSWORD=كلمة-مرور-طويلة-جداً-وفريدة
```

ثم افتح:

```text
https://YOUR-SERVICE/terminal/
```

بعد ما تخلص إدارة رجعه `false`.

## إذا عندك بوت قديم مستقل

فعّل:

```text
ENABLE_RUNNER=true
```

وعدّل `config/apps.toml`. لكن الأفضل للبوتات الجديدة هو Ultra Mode لأن عدة بوتات تشارك نفس Python process والـHTTP pool.

## مهم جداً على Render Free

- الخدمة المجانية تنام بعد الخمول، لذلك استخدم Telegram Webhooks وليس Long Polling.
- الملفات المحلية مؤقتة وتختفي بعد restart/redeploy/spin-down؛ استخدم Database/Object Storage خارجي.
- الـTerminal هنا shell داخل الـcontainer، وليس SSH/VPS كامل.

## فحص البيئة

داخل TitanBox:

```bash
python /app/scripts/doctor.py
```

والـhealth:

```bash
curl https://YOUR-SERVICE/healthz
```

والـmetrics:

```bash
curl https://YOUR-SERVICE/metrics
```

## وين أبدأ بالتطوير؟

ابدأ من `src/titanbox/plugins/default.py` أو أنشئ plugins خاصة بك. لا تحط Whisper أو معالجة PDF ضخمة داخل webhook نفسه؛ ارسل الأعمال الثقيلة إلى Queue/API/Storage خارجي حتى يبقى قلب البوت سريع وخفيف.

# بوت رفع وتحديث الملفات من Telegram

TitanBox v0.2 يتضمن `DeployAdminPlugin`. تقدر تسوي بوت إدارة منفصل وترفع له ZIP أو تحدث ملف واحد بدون Terminal.

مثال Descriptor:

```json
{"name":"deploy-admin","token_env":"DEPLOY_BOT_TOKEN","secret_env":"DEPLOY_BOT_SECRET","plugin":"titanbox.plugins.deploy_admin:DeployAdminPlugin"}
```

وأضف:

```text
DEPLOY_BOT_TOKEN=...
DEPLOY_BOT_SECRET=...
DEPLOY_ADMIN_TELEGRAM_IDS=YOUR_NUMERIC_TELEGRAM_ID
DEPLOY_ROOT=/workspace/titanbox-data
```

نشر كامل: ارسل ZIP وCaption `/deploy mybot`.

تحديث ملف: ارسل الملف وCaption `/put mybot path/to/file.py`.

أو `/use mybot` وبعدها ارسل ملف موجود باسمه؛ إذا الاسم فريد داخل المشروع يحدثه تلقائياً.

راجع `docs/DEPLOY_BOT_AR.md` للتفاصيل والـRollback وربط المشروع بالـRunner.
