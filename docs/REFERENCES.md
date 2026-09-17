# Primary references checked during design

- Render Free instances: https://render.com/docs/free
- Render Docker deployment: https://render.com/docs/docker
- Render Blueprint spec: https://render.com/docs/blueprint-spec
- Render health checks: https://render.com/docs/health-checks
- Render services / deployment model: https://render.com/docs/web-services
- Railway Dockerfiles: https://docs.railway.com/builds/dockerfiles
- Railway services: https://docs.railway.com/services
- Railway volumes: https://docs.railway.com/volumes/reference
- Telegram Bot API webhooks / `secret_token`: https://core.telegram.org/bots/api
- Python security primitives used here: stdlib `hmac`, `hashlib`, `resource`, `zipfile`, `secrets`

The project reads Linux cgroup accounting for container memory and does not infer its quota from host-level RAM totals.
