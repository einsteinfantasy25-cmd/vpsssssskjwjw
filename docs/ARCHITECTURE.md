# TitanBox v1.0 architecture

```text
                         Telegram
                            |
                       HTTPS Webhook
                            |
                            v
              +-----------------------------+
              | TitanBox Control Plane      |
              | Render service/container A  |
              | Deploy Admin only           |
              +-----+-----------+-----------+
                    |           |
                 PostgreSQL    S3-compatible Object Storage
                 jobs/audit    signed releases/backups

Public/Student Bot A -> service/container B -> own DB role/storage namespace/AI
Public/Student Bot B -> service/container C -> own DB role/storage namespace/AI
```

## Boundaries

The control plane remains one bot (`MAX_BOTS_PER_RUNTIME=1`). Ultra Mode process sharing is not a hard security boundary; use it only for trusted components where shared failure is acceptable.

## Durable release protocol

1. Stage locally.
2. Validate ZIP/path/syntax/config/integrity.
3. Upload candidate archive + signed metadata.
4. Activate local release.
5. Restart/health-check when applicable.
6. Promote remote candidate by signed active marker.
7. On failure restore previous state and abandon candidate.

Active markers, not `latest.json`, are authoritative for restore discovery.

## Persistent admin jobs

When PostgreSQL is configured, state-changing admin operations are inserted into `titanbox_jobs` before execution. The worker claims one row transactionally, uses a lease, retries transient failures with backoff and marks permanent validation errors failed. Telegram update IDs form part of the unique key.

## Health semantics

- `/healthz`: process/liveness only; deliberately no remote I/O.
- `/readyz`: bot + required storage/DB readiness.
- `/infra`: live S3/PostgreSQL health from the admin bot.
- `/wakez`: lightweight on-demand wake/check.
