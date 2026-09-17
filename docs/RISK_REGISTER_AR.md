# سجل المخاطر الواقعي — TitanBox v0.4

| الخطر | ما فعله v0.4 | ما يبقى مطلوباً |
|---|---|---|
| سرقة Bot Token | Secrets خارج Git + log redaction | Rotate token فور الاشتباه |
| سرقة Telegram Admin | Allowlist + optional TOTP | فعّل 2FA قبل الاستخدام الجدي |
| ZIP خبيث | traversal/symlink/limits/Unicode/duplicate-path validation | لا تشغل كود غير موثوق داخل control plane |
| Release تغيّر بعد الفحص | SHA-256 manifest + verified rollback + no hardlinks | Git artifact/remote signing أقوى مستقبلاً |
| Bot مزعج/يفشل | per-bot rate/concurrency + circuit breaker | service isolation للبوتات العامة |
| Webhook يتغير/ينمسح | watchdog + repair | external uptime monitor إذا تحتاج تنبيه أثناء النوم |
| Request ضخم | streaming request cap | provider-level DDoS/rate protection خارج التطبيق |
| Secrets في logs | central redaction + repo secret scan | لا تطبع secrets يدوياً؛ provider log policy |
| فساد إداري | HMAC audit chain | audit export خارجي للدوام |
| Render Free يمسح الملفات | تحذير وتصميم stateless | Git + external DB + object storage |
| Render Free ينام | webhook-compatible wake/recovery | paid always-on إذا latency ثابتة مطلوبة |
| Bot A يؤثر على Bot B | control-plane guard | separate services/containers للبوتات المهمة |
| Dependency vulnerable | pinned deps + pip-audit + CodeQL | تحديث دوري ومراجعة alerts |
| Push سيئ يصل Production | CI + `checksPass` auto deploy | branch protection / approvals في GitHub |
