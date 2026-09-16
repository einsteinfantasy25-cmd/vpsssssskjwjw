from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    log_level: str
    admin_token: str | None
    public_base_url: str | None
    bots_json: str
    auto_register_webhooks: bool
    telegram_max_connections: int
    webhook_max_inflight: int
    webhook_handler_timeout_seconds: int
    memory_pressure_limit_pct: int
    enable_runner: bool
    apps_config: Path
    enable_terminal: bool
    terminal_user: str | None
    terminal_password: str | None
    terminal_max_clients: int
    deploy_root: Path
    deploy_admin_ids_raw: str
    deploy_max_upload_bytes: int
    deploy_max_archive_files: int
    deploy_max_extracted_bytes: int
    deploy_keep_releases: int
    deploy_stabilize_seconds: int
    deploy_restart_timeout_seconds: int
    deploy_max_concurrent_ops: int

    @classmethod
    def from_env(cls) -> "Settings":
        public = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or None
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=_int("PORT", 10000, 1, 65535),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            admin_token=os.getenv("ADMIN_TOKEN", "").strip() or None,
            public_base_url=public,
            bots_json=os.getenv("BOTS_JSON", "[]"),
            auto_register_webhooks=_bool("AUTO_REGISTER_WEBHOOKS", False),
            telegram_max_connections=_int("TELEGRAM_MAX_CONNECTIONS", 10, 1, 100),
            webhook_max_inflight=_int("WEBHOOK_MAX_INFLIGHT", 24, 1, 256),
            webhook_handler_timeout_seconds=_int("WEBHOOK_HANDLER_TIMEOUT_SECONDS", 10, 1, 120),
            memory_pressure_limit_pct=_int("MEMORY_PRESSURE_LIMIT_PCT", 90, 50, 99),
            enable_runner=_bool("ENABLE_RUNNER", False),
            apps_config=Path(os.getenv("APPS_CONFIG", "/app/config/apps.toml")),
            enable_terminal=_bool("ENABLE_TERMINAL", False),
            terminal_user=os.getenv("TERMINAL_USER", "").strip() or None,
            terminal_password=os.getenv("TERMINAL_PASSWORD", "").strip() or None,
            terminal_max_clients=_int("TERMINAL_MAX_CLIENTS", 1, 1, 8),
            deploy_root=Path(os.getenv("DEPLOY_ROOT", "/workspace/titanbox-data")),
            deploy_admin_ids_raw=os.getenv("DEPLOY_ADMIN_TELEGRAM_IDS", "").strip(),
            deploy_max_upload_bytes=_int("DEPLOY_MAX_UPLOAD_BYTES", 19_000_000, 1024, 2_000_000_000),
            deploy_max_archive_files=_int("DEPLOY_MAX_ARCHIVE_FILES", 5000, 1, 100000),
            deploy_max_extracted_bytes=_int("DEPLOY_MAX_EXTRACTED_BYTES", 250_000_000, 1024, 5_000_000_000),
            deploy_keep_releases=_int("DEPLOY_KEEP_RELEASES", 6, 2, 100),
            deploy_stabilize_seconds=_int("DEPLOY_STABILIZE_SECONDS", 2, 1, 30),
            deploy_restart_timeout_seconds=_int("DEPLOY_RESTART_TIMEOUT_SECONDS", 12, 2, 120),
            deploy_max_concurrent_ops=_int("DEPLOY_MAX_CONCURRENT_OPS", 1, 1, 4),
        )

    def bot_descriptors(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.bots_json)
        except json.JSONDecodeError as exc:
            raise ValueError("BOTS_JSON is not valid JSON") from exc
        if not isinstance(value, list):
            raise ValueError("BOTS_JSON must be a JSON array")
        return value

    def deploy_admin_ids(self) -> set[int]:
        if not self.deploy_admin_ids_raw:
            return set()
        result: set[int] = set()
        for item in self.deploy_admin_ids_raw.split(","):
            value = item.strip()
            if not value:
                continue
            try:
                result.add(int(value))
            except ValueError as exc:
                raise ValueError("DEPLOY_ADMIN_TELEGRAM_IDS must contain comma-separated integer IDs") from exc
        return result

    def validate(self) -> None:
        if self.enable_terminal:
            if not self.terminal_user or not self.terminal_password:
                raise ValueError("TERMINAL_USER and TERMINAL_PASSWORD are required when terminal is enabled")
            if len(self.terminal_password) < 16:
                raise ValueError("TERMINAL_PASSWORD must be at least 16 characters")
        if self.auto_register_webhooks and not self.public_base_url:
            raise ValueError("PUBLIC_BASE_URL is required when AUTO_REGISTER_WEBHOOKS=true")
        deploy_plugins = [str(x.get("plugin", "")) for x in self.bot_descriptors() if isinstance(x, dict)]
        if any("deploy_admin" in plugin for plugin in deploy_plugins) and not self.deploy_admin_ids():
            raise ValueError("DEPLOY_ADMIN_TELEGRAM_IDS is required for the deployment admin bot")
