# TitanBox v0.4 security model

## Hardened defaults

- Container runs non-root (UID/GID 10001).
- Default image contains no SSH daemon, VNC, browser, Docker daemon, privileged mode, nginx, ttyd, tmux, or editor.
- Optional browser terminal is moved to `Dockerfile.terminal`; it is not present in the hardened image.
- Deploy Admin is private-chat only and authorized by Telegram numeric ID allowlist.
- Optional TOTP 2FA protects sensitive administration even if the Telegram account is compromised.
- Telegram webhook requests require `X-Telegram-Bot-Api-Secret-Token`; Deploy Admin subscribes only to `message` updates.
- Bot tokens/secrets live in platform environment variables, not committed configuration.
- Central log redaction masks known secrets, Telegram-token shapes, and URL credentials.
- Public `/status`, `/readyz`, dashboard details, metrics, and Admin API expose minimal information by default.
- Per-bot concurrency/rate limits, memory-pressure rejection, and a failure circuit breaker contain noisy/failing handlers.
- Webhook request bodies are streamed with a hard size cap before JSON parsing.
- Webhook watchdog verifies and repairs missing/mismatched Telegram webhook URLs.
- Deployment ZIPs reject traversal, absolute/ambiguous paths, symlinks, duplicate normalized paths, oversized archives, invisible/control Unicode names, malformed Python/JSON/TOML, and reserved manifest paths.
- Releases use independent file copies (not hard links), SHA-256 integrity manifests, atomic current switching, and verified rollback.
- Administrative actions are recorded in an append-only JSONL audit chain; when `AUDIT_HMAC_KEY` is present the chain is keyed.
- GitHub CI runs tests, compile/shell checks, repo secret scan, Ruff, dependency audit, CodeQL, and a Docker smoke build.

## Boundaries this code cannot magically provide

A single process is not hard isolation. A child process in the same container is not full isolation. Render Free local storage is not durable. Network-level DDoS mitigation, durable backups, and strict service-to-service isolation require provider/infrastructure choices.

Do not store patient/clinical secrets or regulated medical records in a hobby/free deployment without a separate privacy/security design, appropriate storage, retention controls, and legal/compliance review.
