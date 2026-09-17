# Railway deployment notes — TitanBox v0.4

TitanBox can run as a Docker-based Railway service. Keep the same hardened principles:

- Deploy Admin/control plane separated from public bots where strong isolation is required.
- Store bot tokens/secrets in Railway variables, not Git.
- Set a stable public HTTPS domain for Telegram webhook auto-registration if platform auto-detection is unavailable.
- Treat local filesystem as ephemeral unless you intentionally attach/configure persistent storage.
- Keep terminal/admin API/public metrics off unless intentionally needed.

The supplied `render.yaml` is Render-specific; use Railway service variables to mirror `.env.example`.
