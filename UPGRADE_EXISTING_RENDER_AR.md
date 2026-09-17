# ترقية خدمتك الحالية من v0.3 إلى v0.4

أنت لا تحتاج BotFather جديد ولا Render Service جديد.

## احتفظ بهذه القيم الحالية كما هي

```text
DEPLOY_BOT_TOKEN
DEPLOY_ADMIN_TELEGRAM_IDS
```

ولا تشارك قيمتها مع أحد.

## الخطوات

1. خذ نسخة من Repository الحالي أو أنشئ Branch احتياطية.
2. استبدل محتويات Repository بمحتويات v0.4 كاملة.
3. Commit + Push.
4. Render → Sync Blueprint إن كانت الخدمة مربوطة Blueprint.
5. Deploy latest commit.
6. انتظر حتى `/healthz` يعطي 200.
7. افتح `/status` وتأكد أن version = `0.4.0` و `bots_ready=true`.
8. Telegram → `/diag` ثم `/security`.

## متغيرات v0.4 الجديدة

الـ`render.yaml` الجديد يضبط افتراضياً:

```text
CONTROL_PLANE_ONLY=true
MAX_BOTS_PER_RUNTIME=1
ADMIN_API_ENABLED=false
PUBLIC_STATUS_DETAILS=false
METRICS_PUBLIC=false
WEBHOOK_WATCHDOG_ENABLED=true
WEBHOOK_MAX_BODY_BYTES=1000000
DEPLOY_REQUIRE_2FA=false
```

ويطلب/ينشئ الأسرار المناسبة للـWebhook/Admin/Audit عند إنشاء Blueprint. في خدمة قديمة قد تحتاج Blueprint Sync حتى تدخل القيم الجديدة.

إذا `AUDIT_HMAC_KEY` لم يظهر عندك، أضف قيمة عشوائية طويلة في Render Environment. لا تضعها في GitHub.

## 2FA

خلي `DEPLOY_REQUIRE_2FA=false` أثناء أول Upgrade فقط حتى تتأكد أن كل شيء يعمل. بعدها جهّز TOTP secret وفعّله إذا تريد حماية الأوامر الخطرة حتى لو انسرق حساب Telegram.

## Rollback إذا التحديث نفسه فشل

إذا فشل Docker build قبل نشر v0.4، Render يبقي آخر Deploy ناجح عادةً؛ ارجع GitHub commit السابق ثم Deploy.

إذا v0.4 بدأ لكن Bot لم يصبح Ready، لا تغيّر الكود مباشرة. افحص `/status`, Render Logs و`/diag` إن كان البوت يرد.
