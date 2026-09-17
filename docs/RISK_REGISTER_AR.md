# سجل المخاطر الواقعي — TitanBox v1

| الخطر | دفاع v1 | الباقي الواقعي |
|---|---|---|
| Render Free ينام | wake-on-request, background webhook recovery, watchdog | latency ثابتة تحتاج always-on compute |
| Render يمسح القرص | S3 durable releases + PostgreSQL jobs/audit | provider credentials/retention/backup policy |
| العملية تنقطع بعد أمر Telegram | persistent DB job قبل التنفيذ + unique key + lease recovery | DB نفسها يجب تكون موثوقة |
| Remote backup ناقص بسبب network | candidate/active two-phase protocol | provider outage يبقى ممكناً |
| Remote archive فاسد | SHA-256 | storage writer compromise يحتاج HMAC أيضاً |
| Remote metadata متلاعب | HMAC signing key | rotate key بحذر وحمايته |
| Bot token مسروق | secrets خارج Git + redaction | rotate في BotFather فوراً |
| Telegram Admin account مسروق | allowlist + TOTP | حماية حساب Telegram نفسه ضرورية |
| ZIP خبيث | traversal/symlink/Unicode/duplicate path/size/count checks | لا تشغل كود غير موثوق في control plane |
| Push سيئ | tests/CodeQL/secret scan/dependency audit/checksPass | branch protection/approval أحسن إذا المشروع كبر |
| Bot A يؤثر على Bot B | admin service يمنع أكثر من bot | كل public bot = service/container مستقل |
| OOM/Spam | concurrency/rate/body limits/circuit/cgroup pressure | heavy AI/PDF/audio إلى worker/service خارجي |
| DB/S3 outage | `/readyz`, `/infra`, fail-closed when required | no cloud provider has 100% availability |
| Audit local يختفي | DB audit mirror | external immutable log/SIEM أقوى للمشاريع الكبيرة |
| Signed backup key rotates | verification blocks unknown/tampered backup | keep key stable or maintain explicit key-version rotation |
| Queued rollback يفقد local releases بعد restart | frozen target + durable restore fallback | يحتاج S3 backup لذلك target |
| Retry يعيد side effect | deterministic operation ID + idempotent replay | exact-once موزع غير مدعى |
| latest pointer stale | signed active-marker fallback + pointer self-heal | Object Storage outage يبقى ممكن |
| S3 custom endpoint addressing | auto path-style + explicit override | اتبع متطلبات مزودك إذا مختلفة |
