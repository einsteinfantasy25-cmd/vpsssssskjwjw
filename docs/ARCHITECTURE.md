# TitanBox v0.4 architecture

TitanBox is a lightweight PaaS control plane/runtime, **not a VPS and not a container escape mechanism**.

## Recommended production shape

```text
Telegram Admin
     |
     v
TitanBox Control Plane (service/container A)
     |
     +--> deployment metadata / monitoring / releases

Public Bot A (service/container B) --> external DB / object storage / AI
Public Bot B (service/container C) --> external DB / object storage / AI
```

The Render Blueprint in this release sets `CONTROL_PLANE_ONLY=true` and `MAX_BOTS_PER_RUNTIME=1`, so the existing service is reserved for Deploy Admin. That guard prevents accidentally adding a student/public plugin to the same Python process.

## Ultra Mode

Ultra Mode can run multiple trusted, low-traffic plugins in one FastAPI process with one event loop and shared HTTP pools. It is memory-efficient, but **process sharing is not a hard security boundary**. A plugin bug can affect the shared process.

Use Ultra Mode only where shared-process trust is acceptable. For strong isolation, use separate services/containers and separate secrets/database roles/storage namespaces.

## Legacy Runner

Legacy scripts can be child processes. The runner provides restart backoff, crash-loop protection, file descriptor limits, optional best-effort address-space/file-size limits, reduced priority, and explicit `env_passthrough` secrets.

A child process in the same container is still not equivalent to a separate container/security domain.

## Persistence

Local runtime storage must be treated as disposable unless the host provides a persistent volume. Durable code belongs in Git; durable user data belongs in an external database; durable files/backups belong in object storage.

## Heavy work

Webhook handlers should be short. CPU/RAM-heavy PDF, audio, transcription, OCR, LLM, or video work should use an external worker/service/queue instead of blocking the control plane.
