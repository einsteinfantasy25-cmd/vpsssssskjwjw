# TitanBox v1 security notes

The admin container runs non-root and the hardened Docker image does not expose SSH/VNC/Docker daemon/browser terminal by default. Telegram webhooks require a secret header. Admin actions require Telegram numeric allowlist, and sensitive actions can require TOTP.

Durable release metadata can be authenticated using `RELEASE_SIGNING_KEY` (HMAC-SHA256) in addition to ZIP SHA-256. Do not expose or casually rotate that key.

Secrets are stored in platform environment variables and redacted from application logs/errors. Repository secret scanning is a prevention layer, not permission to commit real credentials.

A Python process is not a hard sandbox between plugins. Strong bot-to-bot isolation means separate services/containers, separate tokens, separate DB roles and separate storage namespaces/credentials.
