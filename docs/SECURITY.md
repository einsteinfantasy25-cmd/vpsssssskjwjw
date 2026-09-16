# Security model

1. The container runs as non-root UID/GID 10001.
2. There is no SSH daemon, VNC server, desktop environment, browser, Docker daemon, or privileged mode.
3. The web terminal is disabled by default and requires both a username and a password of at least 16 characters.
4. Admin API is invisible (404) until `ADMIN_TOKEN` exists, then requires a Bearer token checked with constant-time comparison.
5. Telegram webhook requests require Telegram's `X-Telegram-Bot-Api-Secret-Token` header.
6. Bot tokens are loaded from named environment variables, never from committed config.
7. Legacy child processes receive only a small base environment plus explicitly allow-listed secrets.
8. Child file-descriptor limits and crash-loop protection reduce resource exhaustion risk.
9. Platform TLS should terminate HTTPS. Do not expose ttyd directly without the platform's HTTPS frontend.
10. Keep the terminal disabled except during administration. Rotate a terminal password after sharing screenshots or recordings.

## Important

A writable browser shell is equivalent to code execution inside your container. Do not share its credentials. Free PaaS instances are for hobby/testing use; do not store sensitive medical/patient data there.
