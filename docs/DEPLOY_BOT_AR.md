# Deploy Admin Bot — TitanBox v0.4

## أوامر الفحص

```text
/start
/whoami
/diag
/system
/security
/help
```

## 2FA

إذا فعّلت `DEPLOY_REQUIRE_2FA=true` فالأوامر الحساسة تحتاج جلسة مؤقتة:

```text
/auth 123456
/lock
```

راجع `2FA_AR.md`.

## إدارة المشاريع

```text
/projects
/use NAME
/status [NAME]
/files [NAME] [PREFIX]
/releases [NAME]
/audit [N]
/restart [NAME]
/rollback [NAME] [RELEASE]
```

لرفع ZIP، أرسل الملف وCaption:

```text
/deploy mybot
```

لتحديث ملف واحد:

```text
/put mybot path/to/file.py
```

أو `/use mybot` ثم أرسل ملفاً بلا Caption إذا كان اسمه فريداً داخل المشروع.

## ما الذي يحدث عند Deploy؟

الملف ينزل Streaming تحت حد الحجم، ثم staging وفحص ZIP/path/symlink/Unicode/file-count/expanded-size، ثم Python/JSON/TOML validation، ثم SHA-256 release manifest، ثم atomic activation. Rollback يعيد التحقق من integrity قبل التفعيل.

رفع ZIP **لا يعني تشغيل كود عشوائي تلقائياً**. تشغيل تطبيق مستقل يحتاج Runtime/Runner مقصوداً، وللعزل القوي يفضّل Service/Container مستقل.
