# Deploy on Railway

1. Push the repository to GitHub.
2. Railway -> New Project -> Deploy from GitHub Repo.
3. Railway detects the root `Dockerfile`.
4. Generate a public domain.
5. Add variables from `.env.example` and set `PUBLIC_BASE_URL` to the generated HTTPS domain.
6. Optionally attach a volume if you intentionally need persistent files; TitanBox itself is designed not to require one.
7. If enabling Railway Serverless, expect a cold start after inactivity. Telegram webhooks can wake the service.

Railway currently supports a persistent Volume even on Free/Trial with plan-specific limits; local ephemeral storage is separate. Use external DB/object storage for portable deployments.
