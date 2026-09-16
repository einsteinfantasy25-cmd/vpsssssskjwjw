# Deploy on Render

Render Free is useful for testing/hobby deployments, but it is not a real persistent VPS.

1. Push this folder to a GitHub repository.
2. Render -> New -> Blueprint, or create a Docker Web Service and connect the repo.
3. Select the Free instance if desired.
4. Add secrets from `.env.example` in the dashboard. Never commit real tokens.
5. Set `PUBLIC_BASE_URL` to your `https://...onrender.com` URL.
6. Set `AUTO_REGISTER_WEBHOOKS=true` once the URL is correct, or call the protected admin registration endpoint.
7. Keep `ENABLE_TERMINAL=false` normally.

### Render-specific reality

- A Free web service spins down after 15 minutes without inbound traffic and wakes on the next request.
- The free filesystem is ephemeral; runtime edits disappear after spin-down/restart/redeploy.
- Free services do not provide Render shell/SSH access. TitanBox's optional browser terminal is application-level access to the container, not a real VPS SSH service.
- Free services cannot attach persistent disks.

For Telegram, webhooks are preferable to long polling on a sleeping web service because an incoming webhook can wake it.
