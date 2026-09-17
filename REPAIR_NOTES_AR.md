# إصلاحات v0.4.0

## أخطاء/مخاطر تم إغلاقها

1. Bot واحد كان يستطيع إزعاج global webhook pool → أضيف per-bot semaphore/rate limit.
2. Plugin ينهار باستمرار → failure circuit breaker + cooldown.
3. Webhook ينمسح أو يتغير → watchdog + self-repair.
4. Body كبير قبل parsing → body-size guard.
5. معلومات تشخيصية كانت عامة أكثر من اللازم → status/details/metrics/admin surface أصبحت hardened defaults.
6. Token/secret قد يظهر في error/log → central exact/generic redaction.
7. Telegram account admin إذا انسرق كان وحده كافياً للتعديل → optional TOTP 2FA.
8. Deploy Admin داخل group قد يكشف أو ينفذ أوامر → private-chat only.
9. edited_message قد يحول رسالة قديمة إلى command → تجاهل الإداري منها.
10. Admin spam → admin token bucket.
11. لا يوجد سجل إداري tamper-evident → HMAC audit chain.
12. Release يمكن أن يتغير بعد فحصه → integrity manifest يُراجع قبل activation/rollback.
13. Releases كانت تستفيد من hard links → ألغيت حتى rollback points ما تشارك inode قابل للكتابة.
14. أسماء ملفات تحتوي Unicode bidi/invisible chars → ترفض.
15. `apps.toml` كان يسمح بوضع secrets مباشرة → يرفض أسماء secrets في static env ويوجه إلى env_passthrough.
16. Deploy Admin وBot عام ممكن يعيشان بنفس process بالغلط → CONTROL_PLANE_ONLY + MAX_BOTS_PER_RUNTIME.
17. Default image كان ينزل ttyd/nginx حتى وهوما مطفيين → hardened image ما يحتويهم.

## أشياء لا يستطيع ملف كود واحد حلها

- Persistent storage على Render Free.
- Strict container isolation بين عدة bots داخل Service واحدة.
- DDoS protection على مستوى مزود الشبكة.
- Backup خارجي بدون اختيار مزود تخزين/DB.
- Always-on guarantee على خطة تستعمل sleep.

هذه تحتاج قرار بنية/مزود، مو كود يتظاهر أن القيود غير موجودة.
