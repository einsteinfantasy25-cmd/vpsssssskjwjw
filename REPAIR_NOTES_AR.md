# TitanBox v1.0.0 FINAL — إصلاحات واعتمادية

v1 يحتفظ بإصلاحات الإصدارات السابقة ويضيف طبقة Persistence حقيقية.

- Render URL auto-detection بدون placeholder.
- background webhook registration + watchdog/self-heal.
- missing/wrong bot config لا يسقط الخدمة كلها.
- private-chat admin allowlist + optional TOTP.
- safe ZIP/path/symlink/Unicode/size/count/config validation.
- transactional local releases + integrity manifests + rollback.
- S3-compatible durable releases بنظام candidate -> active حتى النسخة الفاشلة ما تصير latest.
- SHA-256 للـarchive وHMAC-SHA256 للmetadata/active marker عند وجود `RELEASE_SIGNING_KEY`.
- PostgreSQL persistent job queue حتى state-changing admin operation تنحفظ قبل التنفيذ وتقدر ترجع بعد process interruption.
- duplicate Telegram update لا ينشئ job ثانية بسبب unique job key.
- stale running job يرجع queue بعد lease expiry.
- `/healthz` خفيف ومحلي؛ `/readyz` يطبق required infrastructure semantics.
- `/wakez` wake-on-request فقط؛ لا يوجد self-ping loop.
- Render filesystem ما عاد يُعتبر persistence بأي مكان في التصميم.
- Control Plane محمي من خلط Student bots عبر `CONTROL_PLANE_ONLY=true` و`MAX_BOTS_PER_RUNTIME=1`.
- عولج crash window بين نجاح side effect وكتابة Job success عبر idempotent release IDs.
- عولج خطر Rollback retry بدون release صريح الذي كان ممكن يرجع Release إضافية في المحاولة الثانية.
- عولج اعتماد Smart file update على active project الموجود فقط بالRAM.
- عولج ترتيب Remote releases غير الزمني بعد إدخال deterministic job names.
- عولج latest pointer stale/network ambiguity عبر signed active-marker recovery/self-heal.
- عولج احتمال valid remote backup يصير غير قابل للاستعادة فقط لأن ZIP النهائي تجاوز Telegram upload ceiling.
- عولج Cold-start DB pool creation race بـasync lock.
