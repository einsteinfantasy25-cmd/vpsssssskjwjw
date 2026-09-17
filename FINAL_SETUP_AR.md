# TitanBox v1.0.0 FINAL — الإعداد النهائي للمبتدئ

هذا الملف هو الدليل الرئيسي. لا تحتاج تفهم VPS أو Linux حتى تطبق الخطوات.

## الفكرة النهائية

خدمة Render الحالية تبقى **Deploy Admin / Control Plane فقط**. لا نضع بوتات الطلاب داخلها.

```text
Telegram Admin
      |
      v
TitanBox Control Plane (Render)
      |
      +---- GitHub = الكود الدائم
      +---- S3 Object Storage = Releases / Backups الدائمة
      +---- PostgreSQL = Jobs / Audit / Metadata / Idempotency

Student Bot A = Service/Container مستقل
Student Bot B = Service/Container مستقل
```

## المرحلة 1 — ارفع v1 بدون ما تكسر البوت الحالي

1. خذ Backup/Branch من GitHub الحالي.
2. فك ZIP النهائي.
3. ارفع **محتويات** مجلد `TitanBox-1.0.0-FINAL` إلى جذر Repository الحالي.
4. لا تغيّر `DEPLOY_BOT_TOKEN` ولا `DEPLOY_ADMIN_TELEGRAM_IDS` الموجودين في Render.
5. انتظر GitHub Actions.
6. Render -> Sync Blueprint / Deploy latest commit.
7. افتح `/status` وتأكد أن `version=1.0.0`, `loaded_bots=1`, `bots_ready=true`.
8. Telegram: `/diag`, `/security`, `/infra`, `/setup`.

في هذه المرحلة التخزين الخارجي وPostgreSQL يمكن أن يبقيا مطفأين، لذلك الترقية لا تعتمد عليهما.

## المرحلة 2 — فعّل التخزين الدائم

أنشئ Bucket في أي مزود S3-compatible. بعدها Render -> Environment وأضف:

```text
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://ENDPOINT-FROM-YOUR-PROVIDER
S3_REGION=REGION-FROM-YOUR-PROVIDER
S3_BUCKET=YOUR_BUCKET
S3_ACCESS_KEY_ID=YOUR_ACCESS_KEY
S3_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
S3_PREFIX=titanbox
```

لـAWS S3 قد لا تحتاج `S3_ENDPOINT_URL`; استخدم Region الحقيقي. لبعض المزودين مثل R2 يكون Region عادةً قيمة يحددها المزود (غالباً `auto`). انسخ القيم من لوحة المزود ولا تخمنها.

`RELEASE_SIGNING_KEY` موجود في Blueprint كـSecret مولّد. إذا كانت خدمتك القديمة لم تستلمه بعد Sync، أضف Secret عشوائي طويل (32 حرف أو أكثر). **لا تغيّر هذا المفتاح بعد إنشاء Backups موقعة إلا إذا عندك خطة Rotation**؛ تغييره يجعل النسخ القديمة تفشل في فحص HMAC.

عندما `STORAGE_BACKEND=s3` موجود و`DURABILITY_REQUIRED` غير مكتوب، TitanBox يعامل التخزين كـ**مطلوب افتراضياً**. يعني إذا Remote Backup فشل، Release الجديدة لا تصبح النسخة المعتمدة. هذا مقصود حتى ما تتصور عندك Backup وهو غير موجود.

بعد Redeploy أرسل:

```text
/infra
/security
```

نريد `Object Storage: ✅`.

## المرحلة 3 — فعّل PostgreSQL

أنشئ PostgreSQL عند أي مزود موثوق يدعم TLS. انسخ Connection String وضعه في Render فقط:

```text
POSTGRES_DSN=postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require
```

لا تضعه في GitHub ولا Telegram.

عند وجود `POSTGRES_DSN` وغياب `DATABASE_REQUIRED`, TitanBox يجعل قاعدة البيانات **مطلوبة افتراضياً**. السبب: PostgreSQL هنا ليست مجرد إحصائيات؛ هي تحفظ Persistent Admin Jobs حتى عملية `/deploy` أو `/rollback` لا تضيع إذا اختفى Container بعد استلام أمر Telegram.

TitanBox ينشئ جداول Control Plane تلقائياً:

```text
titanbox_meta
titanbox_idempotency
titanbox_audit
titanbox_jobs
```

بعد Redeploy:

```text
/infra
/jobs
```

نريد `PostgreSQL: ✅`.

## شلون صار Deployment آمن ضد انقطاع Render؟

إذا PostgreSQL مفعلة:

```text
Telegram command/document
        |
        v
Persist Job in PostgreSQL
        |
        v
HTTP request can finish
        |
        v
Worker executes job
        |
        +-- success -> succeeded
        +-- temporary failure -> retry with backoff
        +-- process disappears -> stale lease returns job to queue
```

نفس `update_id` من Telegram يعطي Unique Job Key، لذلك Retry من Telegram لا ينشئ عمليتين متطابقتين.

## شلون صار Remote Backup آمن؟

```text
Build local candidate
      |
validate files/syntax/integrity
      |
upload candidate ZIP + metadata to S3
      |
activate/restart locally
      |
health verification
      |
HMAC-sign + active marker
      |
backup becomes restorable
```

إذا التشغيل الجديد يفشل، يرجع Previous Release ولا تتحول Candidate الفاشلة إلى `latest`.

`/restore PROJECT latest` لا يثق بالاسم فقط: يفحص Active Marker + Metadata identity/state + HMAC (إذا Signing Key موجود) + SHA-256 للـZIP ثم يمرر المحتوى عبر نفس Safe ZIP validator قبل الاعتماد.

## Render Free والنوم

TitanBox لا يسوي Self-ping متكرر حتى يتحايل على نوم Render.

الموجود:

```text
https://YOUR-SERVICE.onrender.com/wakez
```

هذا Endpoint خفيف لطلب إيقاظ/فحص **عند الحاجة**. Telegram Webhook نفسه Incoming HTTP request، لذلك الرسالة القادمة تستطيع إيقاظ الخدمة. عند الإقلاع TitanBox يحمل Bot سريعاً ويسجل/يتحقق من Webhook بالخلفية، والـWatchdog يصلحه إذا تغيّر.

إذا تريد تجربة يدوية من جهاز عنده Python:

```bash
python scripts/wake_render.py https://YOUR-SERVICE.onrender.com
```

إذا تحتاج البوت دافئ دائماً وبـlatency ثابتة، الحل الحقيقي Always-on/Paid compute، مو loop داخلي.

## فعّل 2FA قبل الاستخدام الجدي

Render Environment:

```text
DEPLOY_REQUIRE_2FA=true
DEPLOY_TOTP_SECRET=YOUR_BASE32_SECRET
```

استعمل `scripts/generate_totp.py` لإنشاء Secret/URI بدون رفع السر إلى GitHub. بعد ذلك الأوامر الحساسة تحتاج `/auth 123456` والجلسة تنتهي تلقائياً.

## فحص النهاية

Telegram:

```text
/diag
/security
/infra
/jobs
/system
/wake
```

HTTP:

```text
/healthz   = العملية حية فقط
/readyz    = البوت + البنية المطلوبة جاهزة
/status    = حالة عامة بدون أسرار
/wakez     = طلب wake/check خفيف
```

`/healthz` متعمد ما يعتمد على S3/DB حتى outage خارجي ما يسبب Restart loop. `/readyz` هو اللي يفشل بـ503 إذا Backend معلن Required وغير جاهز.

## لا تسوي هذي الأشياء

- لا ترسل Bot Token أو DB URL أو S3 Secret داخل Telegram.
- لا ترفع `.env` إلى GitHub.
- لا تجعل Student Bot داخل نفس Service مال Deploy Admin.
- لا تعتبر Render local filesystem Backup.
- لا تعطل validators حتى تمرر ZIP مرفوض.
- لا تغيّر `RELEASE_SIGNING_KEY` بدون خطة لأن النسخ الموقعة القديمة تعتمد عليه.

## مهم جداً — احفظ مفاتيح الاسترجاع خارج Render

`RELEASE_SIGNING_KEY` و`AUDIT_HMAC_KEY` التي يولدها Render تبقى ثابتة عند Blueprint sync العادي، لكن إذا حذفت الخدمة وأنشأتها من جديد قد تحصل على قيم جديدة. بعد نجاح الإعداد احفظ القيمتين في Password Manager آمن. خصوصاً `RELEASE_SIGNING_KEY`: النسخ القديمة موقعة به ولن نقبلها إذا ضاع المفتاح.

لا تضع هذه المفاتيح في GitHub أو Telegram.

## ملاحظة S3 للمبتدئ

TitanBox يختار `S3_FORCE_PATH_STYLE=true` تلقائياً إذا أعطيت `S3_ENDPOINT_URL` مخصصاً، وهذا يناسب كثير من خدمات S3-compatible مثل R2/MinIO/B2. إذا مزودك يطلب Virtual-host addressing غيّرها يدوياً إلى `false`. مع AWS S3 بدون Custom Endpoint يبقى الافتراضي `false`.

أعطِ Access Key صلاحية أقل ما يمكن: Bucket/Prefix الخاص بـTitanBox فقط، وليس كل حساب التخزين.

## ليش متغيرات Storage وPostgreSQL مو داخل render.yaml؟

هذا متعمد. `render.yaml` لا يدير `STORAGE_BACKEND`, `S3_*`, `POSTGRES_DSN`, `DEPLOY_REQUIRE_2FA`. أضفها يدوياً داخل Render Environment. هكذا Blueprint sync لاحق ما يكتب فوق إعدادات Persistence اللي أنت فعّلتها.

## شنو يصير إذا Render مسح القرص المحلي؟

إذا S3 مفعّل، `/projects` يعرض حتى المشاريع اللي بقت بالسحابة فقط. بعدها:

```text
/restore PROJECT latest
```

ينزل آخر Backup نشط، يفحص HMAC + SHA-256 + ZIP safety ثم يعيد بناء النسخة المحلية. يعني القرص المحلي Cache/Working space، مو مصدر الحقيقة.

## ضمان العمليات بعد Cold Start

مع PostgreSQL، التنفيذ الإداري هو **at-least-once مع side effects idempotent**، مو ادعاء سحري بـexactly-once موزع. قبل التنفيذ نخزن Job؛ Retries لن تختار Rollback مختلف ولا `latest` مختلف لأن الهدف يُثبت إلى Release صريحة عند Queue، وDeploy/Put/Restore تستخدم Operation ID ثابت حتى Retry بعد crash يرجع لنفس Release بدل إنشاء نسخة ثانية.
