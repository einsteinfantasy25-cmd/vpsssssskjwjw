# TitanBox v0.4.0 HARDENED — ملخص الإصدار

v0.4 لا يضيف شكليات فقط؛ يعالج نقاط فشل وأمان حقيقية ظهرت أو كان من الممكن أن تظهر لاحقاً.

## أهم الإضافات

- Control Plane isolation guard: يمنع وضع Bot عام بجانب Deploy Admin بالغلط.
- Max bots/runtime guard لتجنب التداخل غير المقصود.
- Per-bot concurrency + rate limit حتى Bot مزعج لا يستهلك الجميع.
- Circuit breaker للـBot الذي يكرر الأخطاء.
- Webhook watchdog يفحص ويصلح URL المفقود/المتغير.
- أقصى حجم لـWebhook body قبل JSON parsing.
- Secret redaction مركزي للـlogs/errors.
- Public status/details/metrics/Admin API أقل انكشافاً افتراضياً.
- TOTP 2FA اختياري للأوامر الحساسة.
- Admin bot يعمل في private chat فقط ويتجاهل edited messages/callbacks الإدارية.
- Admin rate limit.
- HMAC-chained audit trail.
- SHA-256 manifest لكل Release وفحصه قبل التفعيل/rollback.
- إلغاء hard links بين Releases حتى تعديل inode واحد لا يخرّب rollback points القديمة.
- Reject invisible Unicode control/format characters في filenames/paths.
- Legacy Runner يمنع وضع token/password مباشرة في `apps.toml`.
- Optional process memory/file-size limits للـLegacy Runner.
- Uvicorn connection cap + short keep-alive.
- Hardened Docker image افتراضياً لا يحتوي Web Terminal/nginx/tmux/editor.
- Optional `Dockerfile.terminal` منفصل إذا احتجت Terminal وأنت تقبل attack surface الأكبر.
- CodeQL + dependency audit + test/compile/docker CI.
- Telegram `allowed_updates` أصبح قابل للتحديد؛ Deploy Admin يطلب `message` فقط لتقليل سطح الإدخال.
- Webhook body يُقرأ Streaming بحد صارم حتى chunked requests ما تفرض buffering غير محدود.
- Duplicate update وهو ما يزال In-flight لا يأخذ 200 مبكر؛ يُطلب Retry حتى لا تضيع العملية إذا الطلب الأصلي فشل.
- ZIP duplicate paths بعد normalization تُرفض لمنع extraction-order ambiguity.
- CI يضيف repository secret scan، وRender auto deploy ينتظر `checksPass` بدل نشر commit فاشل مباشرة.
