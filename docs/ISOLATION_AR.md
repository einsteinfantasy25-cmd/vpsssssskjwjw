# العزل بين البوتات — ما هو حقيقي وما هو شكلي؟

## مستويات العزل

```text
نفس Python process   = كفاءة عالية، عزل أمني ضعيف/منطقي فقط
Processes منفصلة     = عزل أخطاء وموارد أحسن، نفس container
Containers/Services  = عزل أمني وموارد أقوى
Services + secrets/DB/storage منفصلة = التصميم الموصى به للبوتات المهمة
```

v0.4 يجعل خدمة الإدارة الحالية Control Plane فقط. لا تضف Medical Bot إليها.

لكل Bot عام مهم استخدم:

- Service/Container مستقل.
- Token مستقل.
- Webhook secret مستقل.
- Database role/credentials مستقلة أو أقل صلاحيات ممكنة.
- Storage prefix/bucket policy مستقلة.
- Rate/concurrency/budget limits مستقلة.

## كيف نثبت أن العزل موجود؟

نفذ اختبارات Chaos/Isolation: إسقاط Bot A، استهلاك RAM/CPU ضمن حدوده، Token خطأ، DB credential خاطئة، storage access خارج namespace، webhook secret متبادل، وتأكد أن Bot B وControl Plane يظلان سليمين.

لا تصف Processes داخل نفس container بأنها "عزل تام"؛ هذا غير صحيح تقنياً.
