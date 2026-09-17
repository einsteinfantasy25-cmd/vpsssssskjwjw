# Checklist قبل ما تعتبر TitanBox جاهز للإدارة الجدية

- [ ] `/status` يعرض `version=0.4.0`, `loaded_bots=1`, `bots_ready=true`.
- [ ] `/diag` يبين Expected webhook = Telegram webhook ولا يوجد Last error.
- [ ] `/security` يبين Control-plane-only ✅ وMax bots/runtime = 1.
- [ ] `DEPLOY_BOT_TOKEN` و`DEPLOY_ADMIN_TELEGRAM_IDS` موجودان في Render Environment فقط.
- [ ] GitHub repository لا يحتوي `.env` أو Token حقيقي؛ CI secret-scan أخضر.
- [ ] GitHub Actions CI + CodeQL أخضر قبل Render deploy.
- [ ] فعّلت TOTP 2FA واختبرت `/auth` ثم `/lock` قبل استخدام أوامر حساسة فعلياً.
- [ ] `AUDIT_HMAC_KEY` موجود كSecret في Render.
- [ ] `ENABLE_TERMINAL=false`, `ADMIN_API_ENABLED=false`, `METRICS_PUBLIC=false` ما لم توجد حاجة واضحة.
- [ ] لا تعتمد على ملفات Render المحلية كنسخة دائمة.
- [ ] البوتات العامة/الطلاب لن تضاف إلى خدمة Control Plane؛ كل بوت مهم يأخذ Service/Container مستقل.
- [ ] قبل تخزين بيانات حقيقية: External DB/Object Storage + backup/restore plan + retention/privacy policy.
