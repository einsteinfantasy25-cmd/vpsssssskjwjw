# رفع TitanBox v1.0.0 إلى GitHub — للمبتدئ

بعد فك ZIP ستجد مجلد `TitanBox-1.0.0-FINAL`. ارفع **المحتويات داخله** إلى جذر repository الحالي.

الصحيح:

```text
repo/
  Dockerfile
  render.yaml
  requirements.txt
  src/
  scripts/
  tests/
  docs/
  .github/
```

الخطأ:

```text
repo/TitanBox-1.0.0-FINAL/Dockerfile
```

لا ترفع `.env` ولا أي Token/Password/DSN/S3 Secret. الأسرار تبقى في Render Environment فقط.

بعد Push انتظر GitHub Actions. `render.yaml` يستخدم `checksPass` حتى الفشل في CI ما يروح تلقائياً للإنتاج.
