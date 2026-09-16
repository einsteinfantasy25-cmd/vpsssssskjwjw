# Troubleshooting

## Render first request is slow
Free Render services spin down after inactivity. The first request may wait for a cold start. This is platform behavior, not a memory leak.

## `free -h` shows enormous RAM
Do not use host totals to infer your container allocation. Check `/healthz` or `/metrics`; TitanBox reads cgroup memory limits directly.

## Changes made in browser terminal vanished
Expected on ephemeral platforms such as Render Free. Commit code to Git and store data externally.

## Webhook returns 403
Verify the bot's webhook `secret_token` matches the environment variable named by `secret_env` in `BOTS_JSON`.

## AppRunner circuit opened
The legacy app crashed too many times inside its configured window. Fix the underlying error, then call the admin start/restart endpoint.

## Out of memory
Disable terminal, reduce legacy processes, move heavy processing off-box, shrink caches, and inspect cgroup memory. Do not increase Uvicorn workers on a 512 MB container unless measurements prove it is safe.
