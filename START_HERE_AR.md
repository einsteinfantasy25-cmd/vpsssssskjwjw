# ابدأ من هنا — TitanBox v1.0.0 FINAL

إذا بوت الإدارة عندك يعمل حالياً، **لا تنشئ BotFather جديد ولا Render Service جديدة**. ارفع v1 على نفس GitHub وخلي Render ينشرها.

الدليل الكامل للمبتدئ: **`FINAL_SETUP_AR.md`**.

أهم شي تفهمه:

```text
Render service الحالية = Deploy Admin فقط
GitHub = الكود الدائم
S3 Object Storage = النسخ/الملفات الدائمة
PostgreSQL = العمليات الدائمة + audit + metadata
Student bots = Services منفصلة لاحقاً
```

أول Upgrade لا يحتاج S3/DB؛ يبقن Disabled حتى تضيف credentials بنفسك إلى Render. ماكو Secret حقيقي داخل ZIP.

بعد Upgrade استخدم:

```text
/diag
/security
/infra
/setup
/wake
```

إذا تريد Persistence فعلية، كمل مراحل S3 ثم PostgreSQL في `FINAL_SETUP_AR.md`.
