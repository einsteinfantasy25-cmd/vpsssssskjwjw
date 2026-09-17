# TitanBox security policy

TitanBox treats Telegram bot tokens, admin tokens, TOTP secrets, database URLs, storage credentials and terminal passwords as secrets.

- Never commit secrets to GitHub.
- Use Render/Railway Environment variables for secrets.
- If a bot token appears in a screenshot, log, commit or chat, revoke/regenerate it in BotFather immediately.
- Keep `ENABLE_TERMINAL=false` on the hardened image.
- Keep `ADMIN_API_ENABLED=false` unless the API is deliberately needed.
- For the Deploy Admin service keep `CONTROL_PLANE_ONLY=true` and `MAX_BOTS_PER_RUNTIME=1`.
- Strict bot-to-bot security isolation requires separate platform services/containers. Ultra Mode plugins in one process are not a security boundary.
- Render Free local storage is ephemeral and must not be the only copy of code/data.

Do not post real tokens or private keys in a public issue. Reproduce security bugs with dummy credentials.
