# التخزين وقاعدة البيانات — المرحلة التالية

لا تجعل Render local filesystem مصدر الحقيقة.

```text
GitHub           = كود/تاريخ الإصدارات
PostgreSQL       = users, settings, jobs, quotas, idempotency
Object Storage   = PDF, audio, images, backups/artifacts
Render local     = temp/staging/cache قابل للحذف
```

عند اختيار DB/Object Storage لاحقاً، استخدم credentials محدودة لكل Bot، TLS، lifecycle/retention للملفات، backups مع restore test، ومفاتيح لا تدخل GitHub.

للبيانات الطبية الحساسة نحتاج تصميم خصوصية منفصل: data minimization, retention/deletion, access controls, encryption, audit, ومراجعة المتطلبات القانونية/المؤسسية المناسبة.
