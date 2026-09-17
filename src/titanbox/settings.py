from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    value = default if raw is None or not raw.strip() else int(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _public_base_url() -> str | None:
    """Resolve a public HTTPS URL without requiring a Render placeholder value."""
    explicit = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit and "placeholder.invalid" not in explicit and "your-service.onrender.com" not in explicit:
        return explicit

    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().strip("/")
    if render_host:
        return f"https://{render_host}"

    railway_host = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
    if railway_host:
        return f"https://{railway_host}"
    return None


def _platform_name() -> str:
    if os.getenv("RENDER", "").strip().lower() == "true":
        return "render"
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return "railway"
    return "generic"


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    log_level: str
    admin_token: str | None
    public_base_url: str | None
    platform: str
    bots_json: str
    auto_register_webhooks: bool
    webhook_secret_key: str | None
    telegram_max_connections: int
    webhook_max_inflight: int
    webhook_handler_timeout_seconds: int
    webhook_registration_retries: int
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
    deploy_storage_persistent: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=_int("PORT", 10000, 1, 65535),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            admin_token=os.getenv("ADMIN_TOKEN", "").strip() or None,
            public_base_url=_public_base_url(),
            platform=_platform_name(),
            bots_json=os.getenv("BOTS_JSON", "[]"),
            auto_register_webhooks=_bool("AUTO_REGISTER_WEBHOOKS", False),
            webhook_secret_key=os.getenv("WEBHOOK_SECRET_KEY", "").strip() or None,
            telegram_max_connections=_int("TELEGRAM_MAX_CONNECTIONS", 10, 1, 100),
            webhook_max_inflight=_int("WEBHOOK_MAX_INFLIGHT", 24, 1, 256),
            webhook_handler_timeout_seconds=_int("WEBHOOK_HANDLER_TIMEOUT_SECONDS", 10, 1, 120),
            webhook_registration_retries=_int("WEBHOOK_REGISTRATION_RETRIES", 3, 1, 10),
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
            deploy_storage_persistent=_bool("DEPLOY_STORAGE_PERSISTENT", False),
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
                parsed = int(value)
            except ValueError as exc:
                raise ValueError("DEPLOY_ADMIN_TELEGRAM_IDS must contain comma-separated integer IDs") from exc
            # v0.2 documentation used 0 as a temporary placeholder. Treat it as unset.
            if parsed == 0:
                continue
            if parsed < 0:
                raise ValueError("DEPLOY_ADMIN_TELEGRAM_IDS must contain positive Telegram user IDs")
            result.add(parsed)
        return result

    def deploy_admin_configured(self) -> bool:
        for item in self.bot_descriptors():
            if isinstance(item, dict) and "deploy_admin" in str(item.get("plugin", "")):
                return True
        return False

    def setup_warnings(self) -> list[str]:
        warnings: list[str] = []
        descriptors = self.bot_descriptors()
        if not descriptors:
            warnings.append("No Telegram bots are configured in BOTS_JSON.")
        if descriptors and self.auto_register_webhooks and not self.public_base_url:
            warnings.append("No public URL could be detected; webhook auto-registration cannot work.")
        if self.deploy_admin_configured() and not self.deploy_admin_ids():
            warnings.append(
                "Deploy Admin has no authorized Telegram user yet. Send /start to the bot to learn your numeric ID, then set DEPLOY_ADMIN_TELEGRAM_IDS."
            )
        if self.platform == "render" and not self.deploy_storage_persistent:
            warnings.append(
                "Render filesystem is ephemeral. Telegram file deployments are not durable across restart/redeploy/spin-down unless external persistence is configured."
            )
        return warnings

    def validate(self) -> None:
        if self.enable_terminal:
            if not self.terminal_user or not self.terminal_password:
                raise ValueError("TERMINAL_USER and TERMINAL_PASSWORD are required when terminal is enabled")
            if len(self.terminal_password) < 16:
                raise ValueError("TERMINAL_PASSWORD must be at least 16 characters")

        descriptors = self.bot_descriptors()
        if self.auto_register_webhooks and descriptors:
            if not self.public_base_url:
                raise ValueError(
                    "A public URL is required when AUTO_REGISTER_WEBHOOKS=true. On Render this is auto-detected from RENDER_EXTERNAL_URL."
                )
            parsed = urlparse(self.public_base_url)
            local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
            if parsed.scheme != "https" and not local_http:
                raise ValueError("PUBLIC_BASE_URL must use HTTPS for Telegram webhooks")
            if not parsed.netloc:
                raise ValueError("PUBLIC_BASE_URL is invalid")

        # Validate admin ID syntax but deliberately allow an empty list. In discovery mode
        # /start and /whoami return the caller's own Telegram ID without granting admin access.
        self.deploy_admin_ids()
