# Railway deployment notes — TitanBox v1

TitanBox يدعم platform-generic التشغيل وRailway URL auto-detection. نفس قواعد الأمان تبقى:

- Deploy Admin وحده في Control Plane service.
- Public bots في services/containers مستقلة.
- الأسرار Environment variables فقط.
- external PostgreSQL/S3-compatible storage للبقاء عبر container replacement ما لم تستخدم Volume مقصود ومفهوم.

Render-specific `render.yaml` لا يطبق على Railway؛ استخدم Dockerfile/railway.toml واضبط environment وفق `.env.example` بدون رفع القيم السرية إلى Git.
