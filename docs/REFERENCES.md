# Primary references checked during design

- Render Free instances: https://render.com/docs/free
- Render Docker deployment: https://render.com/docs/docker
- Render Blueprint spec: https://render.com/docs/blueprint-spec
- Render health checks: https://render.com/docs/health-checks
- Railway Dockerfiles: https://docs.railway.com/builds/dockerfiles
- Railway services/ephemeral storage: https://docs.railway.com/services
- Railway volumes: https://docs.railway.com/volumes/reference
- Railway serverless mode: https://docs.railway.com/deployments/serverless
- Telegram Bot API webhooks and `secret_token`: https://core.telegram.org/bots/api
- ttyd upstream: https://github.com/tsl0922/ttyd

The project does not rely on host-level RAM output to infer its real memory allowance; it reads Linux cgroup accounting instead.
