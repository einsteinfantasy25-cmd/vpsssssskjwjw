# TitanBox v1.0.0 FINAL ULTRA — الحزمة النهائية

هذه الحزمة هي النسخة النهائية للـControl Plane / Deploy Admin على Render، وتجمع الحماية، الاستمرارية، التخزين الخارجي الاختياري، PostgreSQL الاختياري، والـCold-start recovery.

## شنو صار موجود فعلياً؟

- Control Plane فقط على خدمة الإدارة، وبوت واحد كحد افتراضي لمنع خلط بوتات الطلاب مع الإدارة.
- Telegram webhook secret + allowlist + TOTP 2FA اختياري للأوامر الحساسة.
- Rate limit / concurrency / circuit breaker / memory backpressure / body-size caps.
- Safe ZIP validation + transactional releases + SHA-256 manifests + rollback.
- Secret redaction + HMAC chained audit.
- S3-compatible durable releases/backups مع candidate -> activate -> signed active marker.
- PostgreSQL persistent jobs/audit/metadata/idempotency للعمليات الإدارية التي يجب أن تصمد أمام restart/cold-start.
- `/infra`, `/jobs`, `/backups`, `/restore`, `/security`, `/system`, `/diag`.
- `/wakez` و`wake_render.py` لإيقاظ/فحص الخدمة عند الطلب مع retry محدود أثناء الـCold Start فقط.
- Webhook registration بالخلفية + watchdog/self-healing حتى يبقى مسار Telegram قابل للاسترجاع بعد restart.
- GitHub Actions: tests + compile + secret scan + dependency audit + CodeQL + Docker smoke build.

## Render Free والنوم — الحقيقة المهمة

Render Free يمكن أن يوقف Web Service بعد الخمول. لا يوجد كود داخل Container متوقف يقدر يضمن latency فوري أو يبقي نفسه حياً وهو نائم. لذلك TitanBox لا يحتوي self-ping دوري أو traffic مصطنع لتجاوز حدود الخطة.

الاستراتيجية المستخدمة:

1. Telegram webhook نفسه Incoming HTTPS request ويقدر يوقظ الخدمة.
2. `/wakez` endpoint خفيف للاستدعاء اليدوي عند الحاجة.
3. `scripts/wake_render.py` ينتظر Cold Start ويعيد المحاولة ضمن أمر واحد فقط، ثم ينتهي.
4. Bot/plugin loading يسبق فحص S3/PostgreSQL حتى يقل زمن استقبال أول Update.
5. Webhook registration/verification بالخلفية، والـwatchdog يصلحه لاحقاً.
6. PostgreSQL persistent jobs تمنع ضياع عمليات الإدارة الثقيلة بسبب restart بعد استلام الأمر.
7. إذا تحتاج الخدمة جاهزة دائماً بدون Cold Start، الحل الحقيقي Compute always-on.

## مصادر الحقيقة

```text
GitHub          = الكود الدائم
S3/R2/etc.      = ملفات/Backups/Releases الدائمة
PostgreSQL      = Jobs/Audit/Metadata/Idempotency
Render local FS = Cache/working space فقط
```

## العزل

خدمة Deploy Admin تبقى وحدها. كل Bot مهم/عام مستقبلاً يأخذ Service/Container مستقل + Token مستقل + DB role مستقل + Storage prefix/credentials محدودة. هذا هو العزل الأمني الحقيقي؛ Plugins داخل نفس Python process ليست hard security boundary.

## البداية للمبتدئ

ابدأ من `FINAL_SETUP_AR.md` ثم `GITHUB_UPLOAD_AR.md`.
