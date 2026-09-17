# عزل البوتات — TitanBox v1

خدمة TitanBox الحالية هي **Control Plane / Deploy Admin فقط**.

```text
Admin service/container A
  - DEPLOY_BOT_TOKEN
  - Admin DB role
  - Admin storage namespace

Student Bot A service/container B
  - Token A فقط
  - DB role A فقط
  - Storage credentials/prefix A فقط

Student Bot B service/container C
  - Token B فقط
  - DB role B فقط
  - Storage credentials/prefix B فقط
```

`CONTROL_PLANE_ONLY=true` يمنع إضافة Plugin عام داخل خدمة الإدارة بالغلط، و`MAX_BOTS_PER_RUNTIME=1` يمنع noisy-neighbor غير المقصود داخل نفس Process.

Process منفصل أحسن من shared process، لكن **Container/Service مستقل + Secrets/DB roles/Storage scopes مستقلة** هو الحد الأمني الأقوى اللي نعتمد عليه للبوتات المهمة.

اختبارات العزل المستقبلية لكل Bot يجب تشمل: محاولة قراءة secret لبوت ثاني، الوصول لمساره/DB role/storage prefix، CPU/RAM crash isolation، token/webhook cross-routing وcontainer deletion بدون تأثير على الباقين.
