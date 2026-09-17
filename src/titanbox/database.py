from __future__ import annotations

import asyncio
import json
import time
from typing import Any


class DatabaseError(RuntimeError):
    pass


class PostgresDatabase:
    """Small async PostgreSQL infrastructure layer.

    It is intentionally optional. asyncpg is lazy-imported so a no-DB TitanBox does not
    pay startup/memory cost. The tables here belong to the control plane; future public bots
    should use their own DB roles/schema/service for isolation.
    """

    def __init__(self, dsn: str | None, *, min_size: int = 1, max_size: int = 4, timeout_seconds: int = 5):
        self.dsn = dsn
        self.min_size = max(1, int(min_size))
        self.max_size = max(self.min_size, int(max_size))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.pool: Any | None = None
        self._start_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    async def start(self) -> None:
        if not self.enabled or self.pool is not None:
            return
        # The persistent-job worker and the infrastructure health task can both touch the
        # database during a cold start. Serialize pool creation so two asyncpg pools are not
        # created/leaked by that race.
        async with self._start_lock:
            if not self.enabled or self.pool is not None:
                return
            try:
                import asyncpg
            except ImportError as exc:  # pragma: no cover - package contract
                raise DatabaseError("asyncpg is required when POSTGRES_DSN is configured") from exc
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self.dsn,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    timeout=self.timeout_seconds,
                    command_timeout=max(5, self.timeout_seconds * 2),
                    max_inactive_connection_lifetime=60,
                )
                await self._migrate()
            except Exception:
                if self.pool is not None:
                    try:
                        await self.pool.close()
                    except Exception:
                        pass
                    self.pool = None
                raise

    async def close(self) -> None:
        if self.pool is None:
            return
        pool, self.pool = self.pool, None
        await pool.close()

    async def _migrate(self) -> None:
        if self.pool is None:
            raise DatabaseError("Database pool is not started")
        statements = [
            """
            CREATE TABLE IF NOT EXISTS titanbox_meta (
              key TEXT PRIMARY KEY,
              value JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS titanbox_idempotency (
              scope TEXT NOT NULL,
              event_key TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('inflight','completed')),
              expires_at TIMESTAMPTZ NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(scope,event_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS titanbox_idempotency_expiry_idx ON titanbox_idempotency(expires_at)",
            """
            CREATE TABLE IF NOT EXISTS titanbox_audit (
              mac TEXT PRIMARY KEY,
              ts BIGINT NOT NULL,
              actor_id BIGINT,
              action TEXT NOT NULL,
              result TEXT NOT NULL,
              project TEXT,
              payload JSONB NOT NULL,
              inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS titanbox_audit_ts_idx ON titanbox_audit(ts DESC)",
            """
            CREATE TABLE IF NOT EXISTS titanbox_jobs (
              id BIGSERIAL PRIMARY KEY,
              unique_key TEXT NOT NULL UNIQUE,
              kind TEXT NOT NULL,
              payload JSONB NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
              attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 5,
              available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              locked_at TIMESTAMPTZ,
              last_error TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS titanbox_jobs_claim_idx ON titanbox_jobs(state,available_at,id)",
        ]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for statement in statements:
                    await conn.execute(statement)

    async def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "ok": True, "backend": "none"}
        started = time.monotonic()
        try:
            if self.pool is None:
                await self.start()
            async with self.pool.acquire() as conn:
                value = await conn.fetchval("SELECT 1")
            return {
                "enabled": True,
                "ok": value == 1,
                "backend": "postgres",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "pool_min": self.min_size,
                "pool_max": self.max_size,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "ok": False,
                "backend": "postgres",
                "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
            }

    async def put_meta(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        if self.pool is None:
            await self.start()
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO titanbox_meta(key,value,updated_at) VALUES($1,$2::jsonb,NOW())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                """,
                key,
                payload,
            )

    async def get_meta(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        if self.pool is None:
            await self.start()
        async with self.pool.acquire() as conn:
            value = await conn.fetchval("SELECT value FROM titanbox_meta WHERE key=$1", key)
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def idempotency_begin(self, scope: str, event_key: str, *, ttl_seconds: int = 86400) -> str:
        """Return `new`, `inflight` or `completed` using a row-level transaction."""
        if not self.enabled:
            return "new"
        if self.pool is None:
            await self.start()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT state, expires_at <= NOW() AS expired FROM titanbox_idempotency WHERE scope=$1 AND event_key=$2 FOR UPDATE",
                    scope,
                    event_key,
                )
                if row and not row["expired"]:
                    return str(row["state"])
                await conn.execute("DELETE FROM titanbox_idempotency WHERE scope=$1 AND event_key=$2", scope, event_key)
                await conn.execute(
                    """
                    INSERT INTO titanbox_idempotency(scope,event_key,state,expires_at,updated_at)
                    VALUES($1,$2,'inflight',NOW()+($3::text || ' seconds')::interval,NOW())
                    """,
                    scope,
                    event_key,
                    int(ttl_seconds),
                )
                return "new"

    async def idempotency_complete(self, scope: str, event_key: str, *, ttl_seconds: int = 86400) -> None:
        if not self.enabled:
            return
        if self.pool is None:
            await self.start()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE titanbox_idempotency SET state='completed',
                  expires_at=NOW()+($3::text || ' seconds')::interval, updated_at=NOW()
                WHERE scope=$1 AND event_key=$2
                """,
                scope,
                event_key,
                int(ttl_seconds),
            )

    async def idempotency_fail(self, scope: str, event_key: str) -> None:
        if not self.enabled or self.pool is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM titanbox_idempotency WHERE scope=$1 AND event_key=$2", scope, event_key)

    async def append_audit(self, record: dict[str, Any]) -> None:
        if not self.enabled:
            return
        mac = str(record.get("mac") or "")
        if len(mac) != 64:
            return
        if self.pool is None:
            await self.start()
        payload = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO titanbox_audit(mac,ts,actor_id,action,result,project,payload)
                VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
                ON CONFLICT(mac) DO NOTHING
                """,
                mac,
                int(record.get("ts") or 0),
                record.get("actor_id"),
                str(record.get("action") or "")[:80],
                str(record.get("result") or "")[:40],
                str(record.get("project"))[:64] if record.get("project") else None,
                payload,
            )

    @staticmethod
    def _decode_json_value(value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def enqueue_job(
        self,
        unique_key: str,
        kind: str,
        payload: dict[str, Any],
        *,
        max_attempts: int = 5,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise DatabaseError("Persistent job queue requires POSTGRES_DSN")
        if self.pool is None:
            await self.start()
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO titanbox_jobs(unique_key,kind,payload,state,max_attempts)
                VALUES($1,$2,$3::jsonb,'queued',$4)
                ON CONFLICT(unique_key) DO UPDATE SET unique_key=EXCLUDED.unique_key
                RETURNING id,unique_key,kind,payload,state,attempts,max_attempts
                """,
                unique_key[:200],
                kind[:80],
                payload_json,
                min(max(1, int(max_attempts)), 20),
            )
        result = dict(row)
        result["payload"] = self._decode_json_value(result.get("payload"))
        return result

    async def claim_job(self, kinds: tuple[str, ...], *, lease_seconds: int = 600) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        if self.pool is None:
            await self.start()
        if not kinds:
            return None
        lease_seconds = min(max(30, int(lease_seconds)), 3600)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # A container can disappear after acknowledging a webhook. Recover a job whose
                # worker vanished once the lease expires.
                await conn.execute(
                    """
                    UPDATE titanbox_jobs
                    SET state='queued', locked_at=NULL, available_at=NOW(), updated_at=NOW(),
                        last_error=COALESCE(last_error,'worker lease expired')
                    WHERE state='running' AND locked_at < NOW()-($1::text || ' seconds')::interval
                      AND attempts < max_attempts
                    """,
                    lease_seconds,
                )
                # If the worker disappeared during the final allowed attempt, do not leave
                # the row stuck in `running` forever. Close it as failed and surface it in
                # /jobs for an explicit operator retry with a new Telegram update.
                await conn.execute(
                    """
                    UPDATE titanbox_jobs
                    SET state='failed', locked_at=NULL, updated_at=NOW(),
                        last_error=COALESCE(last_error,'worker lease expired on final attempt')
                    WHERE state='running' AND locked_at < NOW()-($1::text || ' seconds')::interval
                      AND attempts >= max_attempts
                    """,
                    lease_seconds,
                )
                row = await conn.fetchrow(
                    """
                    SELECT id FROM titanbox_jobs
                    WHERE state='queued' AND available_at <= NOW() AND kind = ANY($1::text[])
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    list(kinds),
                )
                if row is None:
                    return None
                job_id = int(row["id"])
                claimed = await conn.fetchrow(
                    """
                    UPDATE titanbox_jobs
                    SET state='running', attempts=attempts+1, locked_at=NOW(), updated_at=NOW()
                    WHERE id=$1
                    RETURNING id,unique_key,kind,payload,state,attempts,max_attempts
                    """,
                    job_id,
                )
        result = dict(claimed)
        result["payload"] = self._decode_json_value(result.get("payload"))
        return result

    async def complete_job(self, job_id: int) -> None:
        if not self.enabled or self.pool is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE titanbox_jobs SET state='succeeded',locked_at=NULL,last_error=NULL,updated_at=NOW() WHERE id=$1",
                int(job_id),
            )

    async def fail_job(
        self,
        job_id: int,
        error: str,
        *,
        retry: bool,
        retry_delay_seconds: int = 5,
    ) -> str:
        if not self.enabled or self.pool is None:
            return "failed"
        error = str(error).replace("\n", " ")[:500]
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT attempts,max_attempts FROM titanbox_jobs WHERE id=$1", int(job_id))
            if row is None:
                return "failed"
            can_retry = bool(retry) and int(row["attempts"]) < int(row["max_attempts"])
            state = "queued" if can_retry else "failed"
            delay = min(max(1, int(retry_delay_seconds)), 900)
            if can_retry:
                await conn.execute(
                    """
                    UPDATE titanbox_jobs SET state='queued',locked_at=NULL,last_error=$2,
                      available_at=NOW()+($3::text || ' seconds')::interval,updated_at=NOW()
                    WHERE id=$1
                    """,
                    int(job_id),
                    error,
                    delay,
                )
            else:
                await conn.execute(
                    """
                    UPDATE titanbox_jobs SET state='failed',locked_at=NULL,last_error=$2,updated_at=NOW()
                    WHERE id=$1
                    """,
                    int(job_id),
                    error,
                )
            return state

    async def recent_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        if self.pool is None:
            await self.start()
        limit = min(max(1, int(limit)), 100)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id,unique_key,kind,state,attempts,max_attempts,last_error,created_at,updated_at
                FROM titanbox_jobs ORDER BY id DESC LIMIT $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

    async def cleanup_expired_idempotency(self) -> int:
        if not self.enabled or self.pool is None:
            return 0
        async with self.pool.acquire() as conn:
            status = await conn.execute("DELETE FROM titanbox_idempotency WHERE expires_at <= NOW()")
        try:
            return int(str(status).split()[-1])
        except Exception:
            return 0
