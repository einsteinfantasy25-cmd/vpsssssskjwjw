# TitanBox v1.0.0 FINAL — ملخص الإصدار

هذا الإصدار يجمع Hardening v0.4 مع طبقة Persistence وCold-start recovery.

## Reliability

- S3-compatible durable release backups.
- Two-phase backup commit: candidate لا تصبح Active إلا بعد نجاح activation/health.
- SHA-256 verification + HMAC authenticity للmetadata/active markers عند وجود `RELEASE_SIGNING_KEY`.
- PostgreSQL persistent jobs للـdeploy/restart/rollback/restore.
- Duplicate Telegram retry -> نفس Unique Job وليس عملية ثانية.
- Stale running job lease -> يعود Queue بعد اختفاء worker.
- `/restore` يمر عبر نفس validators ولا يشغل Remote ZIP مباشرة.
- Required backend failure يظهر في `/readyz` بدون تحويل `/healthz` إلى restart loop.

## Cold start / Render

- `/wakez` endpoint خفيف للطلب عند الحاجة.
- Telegram webhook نفسه Incoming request ويمكنه إيقاظ الخدمة على منصات wake-on-request.
- Bot loading قبل external infrastructure validation.
- webhook registration/verification بالخلفية.
- webhook watchdog/self-healing.
- لا يوجد self-ping loop لتجاوز نوم الخطة.

## Security

- Control-plane-only + max 1 bot/runtime.
- non-root, no default SSH/VNC/terminal.
- Telegram webhook secret verification.
- rate/concurrency/circuit/memory pressure containment.
- secret redaction.
- TOTP 2FA للأوامر الحساسة.
- HMAC-chained audit + optional durable PostgreSQL mirror.
- safe ZIP extraction and release integrity manifests.
- generated release signing key.
- CI/CodeQL/dependency/secret/Docker checks.

حدود صريحة: لا يوجد برنامج يضمن منع كل failure أو compromise مستقبلاً. العزل التام بين تطبيقات مختلفة يحتاج Containers/Services مستقلة، والـalways-on الحقيقي يحتاج compute لا ينام.

## إضافات الاعتمادية الأخيرة

- Persistent document jobs لا تعتمد على `/use` الموجود بالRAM؛ يتحول Smart Update إلى `/put PROJECT PATH` صريح قبل دخوله PostgreSQL.
- Rollback وRestore `latest` يثبتان Target صريح قبل Queue حتى Retry بعد crash ما يتحرك إلى Release ثانية.
- Deploy/Put/Restore تستخدم deterministic Operation ID لمنع إنشاء Release ثانية عند replay.
- إذا queued Rollback فقد نسخه المحلية بسبب Render restart، يقدر يرجع لنفس Target من Durable Storage إذا موجود.
- ترتيب Durable backups يعتمد signed `activated_at` وليس الاسم.
- signed latest pointer self-heals من Active Markers إذا صار stale بسبب network ambiguity.
- Restore من S3 لا ينكسر بسبب Telegram upload limit؛ له internal bounded restore limit مستقل بعد HMAC/SHA verification.
- PostgreSQL pool startup صار serialized حتى Cold Start ما ينشئ Poolين بسبب race بين worker وhealth task.
- Custom S3 endpoints default إلى path-style مع override متاح.


## Final verification

- 101 automated tests passed.
- Real ASGI smoke passed for `/healthz`, `/wakez`, `/status`, `/readyz`.
- Authenticated webhook stress smoke: 1,500 requests, concurrency 50, zero failures; wrong secret returned 403.
- Exact Render performance is not guaranteed by local benchmarks.
