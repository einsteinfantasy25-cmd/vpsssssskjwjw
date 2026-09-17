# TitanBox v1 — Object Storage + PostgreSQL

## Object Storage

TitanBox يتعامل مع S3-compatible APIs. الاستخدام الحالي داخل Deploy Admin هو Durable Releases/Backups. البوتات المستقبلية تقدر تستخدم نفس abstraction لكن **الأفضل لكل Bot مستقل credentials/prefix خاص به**.

Environment:

```text
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://...
S3_REGION=...
S3_BUCKET=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PREFIX=titanbox
```

اختياري:

```text
S3_FORCE_PATH_STYLE=false
S3_SERVER_SIDE_ENCRYPTION=
DURABLE_KEEP_RELEASES=20
DURABILITY_REQUIRED=true
```

إذا `DURABILITY_REQUIRED` محذوف وStorage مفعلة، v1 يجعلها true افتراضياً.

`RELEASE_SIGNING_KEY` يوقع metadata والactive marker بـHMAC-SHA256. SHA-256 وحده يكشف فساد الملف، لكن HMAC يضيف Authentication ضد تعديل metadata بدون امتلاك Signing Key.

## PostgreSQL

```text
POSTGRES_DSN=postgresql://...
DB_POOL_MIN=1
DB_POOL_MAX=4
DB_CONNECT_TIMEOUT_SECONDS=5
```

إذا `DATABASE_REQUIRED` محذوف وDSN موجود، v1 يجعل DB Required افتراضياً.

Control-plane schema:

- `titanbox_meta`
- `titanbox_idempotency`
- `titanbox_audit`
- `titanbox_jobs`

هذا DB مال Control Plane. Student Bot لاحقاً لا نعطيه نفس Admin DB role.

## Outage behavior

S3 required + S3 down: Release الجديدة لا تُعتمد.

DB required + DB down: `/readyz` يصير 503، وstate-changing persistent admin operations تفشل بوضوح بدل التنفيذ بنصف ضمانات.

`/healthz` يبقى 200 إذا العملية نفسها حية حتى ما outage خارجي يسبب restart loop.

## تفاصيل الاعتمادية في v1

- Remote release يبدأ `candidate` وغير قابل للاستعادة.
- بعد نجاح Local activation/health فقط يتحول `active`.
- Signed `latest.json` يُكتب كجزء من Commit، وليس مجرد اسم غير موثوق.
- ترتيب Backups يعتمد `activated_at` داخل Active Marker الموقّع، وليس اسم Release؛ هذا مهم لأن Persistent Jobs تستخدم أسماء idempotent غير زمنية.
- Restore يتحقق من HMAC للـmetadata/marker ومن SHA-256 للـarchive، ويعمل Head/size preflight إذا Backend يدعمه قبل تنزيل الملف.
- إذا latest pointer صار stale بسبب network ambiguity، TitanBox يرجع للـactive markers الموقعة ويصلح pointer تلقائياً.
- `/projects` يكتشف المشاريع الموجودة فقط في Object Storage بعد فقدان القرص المحلي.

لـCustom S3 Endpoint، Path-style addressing يتفعل تلقائياً ما لم تحدد `S3_FORCE_PATH_STYLE=false` صراحةً.

## PostgreSQL Job semantics

Admin mutations تُخزن أولاً كJobs. Worker يستخدم lease + retry/backoff. إذا مات الـContainer، Job running يرجع queued بعد انتهاء lease؛ وإذا مات في آخر محاولة لا يبقى stuck إلى الأبد بل يغلق `failed`. عمليات Deploy/Put/Restore تستخدم Operation ID ثابت، وRollback/Restore target يتجمد عند enqueue حتى Retry لا يتحول إلى هدف آخر.
