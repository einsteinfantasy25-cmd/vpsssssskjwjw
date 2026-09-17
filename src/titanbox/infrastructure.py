from __future__ import annotations

import asyncio
import logging
from typing import Any

from .database import PostgresDatabase
from .storage import DurableReleaseStore, S3ObjectStore, StorageConfig

log = logging.getLogger("titanbox.infrastructure")


class InfrastructureManager:
    def __init__(self, settings: Any):
        self.settings = settings
        store: S3ObjectStore | None = None
        if settings.storage_backend == "s3":
            store = S3ObjectStore(
                StorageConfig(
                    backend="s3",
                    endpoint_url=settings.s3_endpoint_url,
                    region=settings.s3_region,
                    bucket=settings.s3_bucket,
                    access_key_id=settings.s3_access_key_id,
                    secret_access_key=settings.s3_secret_access_key,
                    prefix=settings.s3_prefix,
                    force_path_style=settings.s3_force_path_style,
                    server_side_encryption=settings.s3_server_side_encryption,
                )
            )
        self.object_store = store
        self.releases = DurableReleaseStore(
            store,
            keep_releases=settings.durable_keep_releases,
            signing_key=settings.release_signing_key,
        )
        self.database = PostgresDatabase(
            settings.postgres_dsn,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            timeout_seconds=settings.db_connect_timeout_seconds,
        )
        self._startup: dict[str, Any] = {
            "storage": {"enabled": self.releases.enabled, "ok": not settings.durability_required},
            "database": {"enabled": self.database.enabled, "ok": not settings.database_required},
        }

    async def start(self) -> None:
        async def start_db() -> None:
            if not self.database.enabled:
                self._startup["database"] = {"enabled": False, "ok": True, "backend": "none"}
                return
            try:
                await self.database.start()
                self._startup["database"] = await self.database.health()
            except Exception as exc:
                self._startup["database"] = {
                    "enabled": True,
                    "ok": False,
                    "backend": "postgres",
                    "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                }
                log.exception("database startup check failed")

        async def check_storage() -> None:
            if not self.releases.enabled:
                self._startup["storage"] = {"enabled": False, "ok": True, "backend": "none"}
                return
            try:
                self._startup["storage"] = await self.releases.health()
            except Exception as exc:
                self._startup["storage"] = {
                    "enabled": True,
                    "ok": False,
                    "backend": "s3",
                    "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                }
                log.exception("storage startup check failed")

        # Bound cold-start cost. The service still boots in degraded mode and exposes diagnosis.
        try:
            await asyncio.wait_for(
                asyncio.gather(start_db(), check_storage()),
                timeout=self.settings.infra_startup_timeout_seconds,
            )
        except TimeoutError:
            log.warning("infrastructure startup validation timed out; continuing in degraded mode")

    async def close(self) -> None:
        await self.database.close()

    def required_ready(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self.settings.durability_required and not bool(self._startup.get("storage", {}).get("ok")):
            reasons.append("durable_storage_not_ready")
        if self.settings.database_required and not bool(self._startup.get("database", {}).get("ok")):
            reasons.append("database_not_ready")
        return not reasons, reasons

    async def health(self) -> dict[str, Any]:
        storage_task = asyncio.create_task(self.releases.health())
        db_task = asyncio.create_task(self.database.health())
        storage, database = await asyncio.gather(storage_task, db_task)
        ok = bool(storage.get("ok")) and bool(database.get("ok"))
        if self.settings.durability_required:
            ok = ok and bool(storage.get("enabled"))
        if self.settings.database_required:
            ok = ok and bool(database.get("enabled"))
        return {
            "ok": ok,
            "storage": storage,
            "database": database,
            "durability_required": self.settings.durability_required,
            "database_required": self.settings.database_required,
        }
