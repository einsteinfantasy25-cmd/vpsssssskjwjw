# TitanBox v1 troubleshooting

## `/start` لا يرد

`/status`: إذا `loaded_bots=0`, راجع Render Logs و`DEPLOY_BOT_TOKEN`. إذا loaded لكن مو ready، قارن Webhook من `/diag`.

## `/readyz` = 503 لكن `/healthz` = 200

هذا ممكن ومقصود. افتح `/readyz` وشوف reasons ثم `/infra`. إذا S3/DB معلنة Required وفاشلة، TitanBox يبقى حي للتشخيص لكنه يقول إنه غير Ready.

## S3 مفعلة وDeployment يرفض

إذا storage required، هذا Fail-closed. استخدم `/infra`; صحح endpoint/bucket/keys/permissions. لا تجعل `DURABILITY_REQUIRED=false` فقط حتى يمر Deploy إلا إذا تقبل صراحة فقدان الـbackup.

## Backup موجود لكن `/restore` يرفض signature

لا تتجاوز الفحص. إما metadata/marker تغير أو `RELEASE_SIGNING_KEY` تغير. رجع المفتاح الصحيح أو استخدم artifact موثوق معروف المصدر.

## PostgreSQL down

`/infra` يبين الخطأ. إذا Persistent Job لم يتم تثبيتها بنجاح، TitanBox لا يدعي نجاح العملية. بعد رجوع DB، أعد الأمر. Jobs التي كانت مثبتة يمكن للworker استئنافها.

## Job بقي running بعد crash

الworker يستخدم lease. بعد انتهاء lease يرجع stale job إلى queue إذا attempts ما تجاوزت الحد. `/jobs` يبين state/attempts/error.

## Render نام

أول Incoming request يصحيه. افتح `/wakez` أو أرسل للبوت وانتظر cold start. لا تعمل self-ping loop داخل TitanBox. إذا تحتاج latency ثابتة استخدم always-on compute.

## ملفات local اختفت

طبيعي على ephemeral filesystem. استعمل `/backups PROJECT` و`/restore PROJECT latest` إذا S3 مفعلة. كود الإنتاج الدائم يبقى Git أيضاً.

## `CONTROL_PLANE_ONLY` يمنع Bot جديد

مقصود. أنشئ خدمة/Container منفصلة للبوت العام.
