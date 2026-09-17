# Deploy Admin Bot — TitanBox v1

## أهم الأوامر

```text
/diag
/security
/infra
/setup
/wake
/jobs [N]
/projects
/use NAME
/status [NAME]
/files [NAME]
/releases [NAME]
/backups [NAME]
/restore NAME [RELEASE|latest]
/restart [NAME]
/rollback [NAME] [RELEASE]
```

ZIP كامل:

```text
Caption: /deploy mybot
```

ملف واحد:

```text
Caption: /put mybot path/to/file.py
```

إذا PostgreSQL مفعلة، العمليات المعدلة للحالة تُحفظ كPersistent Job قبل التنفيذ. إذا S3 مفعلة، Release الناجحة تحصل Durable signed backup. `/restore` يسترجع النسخة ثم يعيد التحقق منها محلياً قبل اعتمادها.

بوت الإدارة يقبل private fresh messages فقط، ويستخدم Admin ID allowlist. فعّل TOTP للأوامر الحساسة قبل الاستخدام الجدي.
