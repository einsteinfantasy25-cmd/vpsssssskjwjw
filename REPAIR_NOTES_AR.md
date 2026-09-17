# حزمة إصلاح TitanBox v0.3.0

## المشاكل التي عالجتها هذه النسخة

### 1. Render Free رفض Blueprint
حُذف الاعتماد على أي setting غير مناسب للخطة المجانية، خصوصاً الخطأ السابق المتعلق بـ `maxShutdownDelaySeconds`.

### 2. Docker كان يعطي `/src not found`
Dockerfile لم يعد يعمل `COPY src`, `COPY config`, `COPY nginx` بشكل منفصل. الآن يعمل COPY واحد للـrepo ثم يفحص الملفات الإلزامية برسالة واضحة.

### 3. `PUBLIC_BASE_URL` المؤقت
TitanBox يكتشف تلقائياً `RENDER_EXTERNAL_URL` أو `RENDER_EXTERNAL_HOSTNAME`. لا يحتاج Placeholder على Render.

### 4. Webhook لم يكن يسجل تلقائياً
Blueprint النهائي يضع:

```text
AUTO_REGISTER_WEBHOOKS=true
```

ويتحقق من Telegram عبر `getMe → setWebhook → getWebhookInfo` مع Retry.

### 5. Webhook secret
Render `generateValue` يولد base64 وقد يحتوي رموز لا يقبلها Telegram في `secret_token`. لذلك v0.3 لا يرسل القيمة المولدة نفسها إلى Telegram؛ يستخدمها كمفتاح داخلي ويشتق منها secret آمن مكوّن فقط من الأحرف المسموحة.

### 6. `/start` كان يسكت عند Admin ID خطأ
المستخدم غير المصرح لا يُعطى صلاحيات، لكن `/start` و`/whoami` يعرضان Telegram numeric ID الخاص به والتعليمات. لا يوجد تنفيذ إداري قبل إضافته للـallowlist.

### 7. خطأ Bot واحد كان يستطيع إسقاط TitanBox كله
أخطاء تحميل Bot/Token/plugin أصبحت معزولة لكل bot. TitanBox يبقى Live وتظهر المشكلة في `/status` و`/readyz`.

### 8. الرابط كان غير مفهوم
`/` أصبح Dashboard واضحة. أضيف `/setup` و`/status` و`/readyz` للتشخيص.

### 9. تشخيص Telegram
أضيف `/diag` داخل Admin bot ليعرض:

- `getMe`
- Telegram username
- Expected webhook
- Actual webhook
- pending update count
- last Telegram webhook error

### 10. Admin ID = 0
القيمة `0` القديمة تُعامل كـ"غير مضبوط"، وليس كـAdmin وهمي.

### 11. GitHub repository ناقص
أضيف `scripts/preflight_repo.py`، واختبار CI لعقد الـrelease tree.

### 12. سلامة الإعدادات
- HTTPS مطلوب للـTelegram webhook خارج localhost.
- Tokens لا تُكتب داخل BOTS_JSON.
- Terminal يبقى OFF افتراضياً.
- Memory/backpressure limits باقية.
- ZIP traversal/symlink/file count/size validation باقية.

### 13. منع الوعد الكاذب بالـPersistence
إذا TitanBox يعمل على Render والـstorage غير معلن كدائم، Admin bot يعرض تحذيراً بعد عمليات الملفات. Render Free لا يحفظ filesystem بعد restart/redeploy/spin-down.

### 14. رفع ZIP ≠ تشغيل أي برنامج تلقائياً
النسخة توضح هذا صراحة. المشروع المستقل يجب أن يكون مربوطاً بالـRunner أو مبنياً كـUltra Mode plugin.
