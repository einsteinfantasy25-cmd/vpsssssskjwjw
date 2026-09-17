# TitanBox v0.4.0 HARDENED — البداية السريعة

إذا عندك v0.3 شغال على Render، **لا تنشئ بوت إدارة جديد ولا خدمة جديدة**.

1. ارفع محتويات هذه الحزمة إلى جذر GitHub repository بدل ملفات v0.3.
2. احتفظ بقيم Render الحالية `DEPLOY_BOT_TOKEN` و`DEPLOY_ADMIN_TELEGRAM_IDS` كما هي.
3. Render → Sync Blueprint/Deploy latest commit.
4. افتح `/status` وتأكد من `version=0.4.0`, `loaded_bots=1`, `bots_ready=true`.
5. في Telegram أرسل `/diag` ثم `/security` ثم `/system`.
6. بعد التأكد من الاستقرار، فعّل 2FA حسب `docs/2FA_AR.md`.

النسخة الافتراضية تجعل خدمة Render الحالية **Control Plane فقط**: Deploy Admin وحده. لا تضف بوتات الطلاب إلى نفس الخدمة إذا كان هدفك عزل أمني قوي.

ابدأ بالتفصيل من `START_HERE_AR.md`.
