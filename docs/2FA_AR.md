# تفعيل 2FA لبوت الإدارة

الهدف: سرقة حساب Telegram وحدها ما تكفي لتنفيذ Deploy/Rollback/تعديل الملفات.

## إنشاء Secret

على جهاز موثوق داخل نسخة المشروع:

```bash
python scripts/generate_totp.py --account titanbox-admin
```

سيظهر Base32 secret ورابط `otpauth://...`. أضفه إلى تطبيق Authenticator موثوق. **لا ترسل Secret إلى Telegram، ولا تصوره، ولا ترفعه إلى GitHub.**

## Render Environment

ضع:

```text
DEPLOY_TOTP_SECRET=<BASE32 secret>
DEPLOY_REQUIRE_2FA=true
```

ثم Redeploy.

## الاستخدام

قبل أمر حساس:

```text
/auth 123456
```

الجلسة الافتراضية 5 دقائق. بعدها نفذ `/deploy`, `/put`, `/rollback`, `/restart` أو أوامر قراءة المشاريع المحمية. لإغلاقها فوراً:

```text
/lock
```

الكود نفسه لا يُحفظ في Audit log، ونفس TOTP counter لا يُقبل مرتين في نفس runtime.

إذا ضاع الـAuthenticator، عطّل `DEPLOY_REQUIRE_2FA` من Render Environment بعد التحقق من ملكية حساب الاستضافة ثم أعد إعداد Secret جديد.
