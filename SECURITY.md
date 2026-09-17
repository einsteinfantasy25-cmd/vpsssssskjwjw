# TitanBox v1.0.0 security policy

Secrets include Telegram bot tokens, admin tokens, webhook keys, TOTP secrets, audit/signing keys, PostgreSQL DSNs, S3 access keys and terminal passwords.

- Never commit secrets to GitHub.
- Keep Deploy Admin in a private Telegram chat and allow only numeric admin IDs.
- Enable TOTP before serious administration.
- Keep `CONTROL_PLANE_ONLY=true` and `MAX_BOTS_PER_RUNTIME=1` on the admin service.
- Keep terminal/Admin HTTP API/public metrics disabled unless deliberately required.
- Use separate service/container + token + DB role + storage namespace for each important public bot.
- `RELEASE_SIGNING_KEY` must remain private and stable; it authenticates durable release metadata.
- If any credential appears in a screenshot, log, commit or public chat, rotate/revoke it immediately.
- Render local storage is disposable; use external persistence for durable data.
- Do not treat student/patient/medical data as ordinary bot logs. Use data minimization, retention/deletion, access control and institutional/legal review before handling sensitive records.

Additional recovery rules:

- Save `RELEASE_SIGNING_KEY` and `AUDIT_HMAC_KEY` in a secure password manager after provisioning; recreating a Render service can generate new secrets.
- Object-storage credentials should be least-privilege and restricted to TitanBox's bucket/prefix when the provider supports it.
- A signed backup whose marker/metadata fails integrity checks is never silently restored.
- Persistent admin jobs use idempotent/frozen targets to reduce duplicate side effects after process loss; distributed exact-once semantics are not claimed.
