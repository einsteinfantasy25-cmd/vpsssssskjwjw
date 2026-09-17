# Render Free — النوم والإيقاظ بدون حيل

Render Free يمكن أن يوقف الخدمة بعد الخمول. TitanBox لا يعمل self-ping loop ولا traffic مصطنع لتجاوز سياسة الخطة.

## شنو يصير عند رسالة Telegram؟

إذا Webhook مسجل، Telegram يرسل HTTPS POST إلى Render. هذا Incoming HTTP request ويقدر يسبب spin-up. خلال Cold Start قد يتأخر الرد؛ Telegram يعيد محاولة Webhook إذا لم يحصل على 2xx.

TitanBox يقلل زمن recovery عبر:

- تحميل Bot/plugin قبل فحص S3/DB الخارجي.
- Webhook registration/verification بالخلفية.
- Webhook watchdog لإصلاح URL/registration.
- Persistent PostgreSQL jobs حتى العملية الإدارية الثقيلة لا تعتمد فقط على عمر Process.

## `/wakez`

```text
https://YOUR-SERVICE.onrender.com/wakez
```

Endpoint خفيف جداً بدون DB/S3 calls. يستخدم Wake/check عند الحاجة فقط.

CLI يدوي:

```bash
python scripts/wake_render.py https://YOUR-SERVICE.onrender.com
```

## الشي اللي ما نكدر نحلّه بالكود

إذا تحتاج أول رد دائماً فوري وما تريد Cold Start نهائياً، لازم Compute always-on. ماكو كود داخل Container نائم يقدر يشتغل وهو أصلاً متوقف من المنصة.

`scripts/wake_render.py` في v1 يعمل Retry مؤقت فقط أثناء أمر الإيقاظ الحالي (HTTP 5xx/timeouts)، وينتهي عند النجاح أو انتهاء المهلة. ما يبقى شغال بالخلفية وما يسوي keepalive دوري.

مهم: أي Web Service عامة ممكن أحد يرسل إلها HTTP request، لذلك ماكو كود داخل التطبيق يضمن منع طرف خارجي من إيقاظ Free service. إذا تحتاج SLA/latency ثابتة، استخدم Always-on compute بدل الاعتماد على sleep/wake.
