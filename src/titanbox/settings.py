from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_BASE32_RE = re.compile(r"^[A-Z2-7]+=*$")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
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
    admin_api_enabled: bool
    public_status_details: bool
    metrics_public: bool
    public_base_url: str | None
    platform: str
    control_plane_only: bool
    max_bots_per_runtime: int
    bots_json: str
    auto_register_webhooks: bool
    webhook_secret_key: str | None
    telegram_max_connections: int
    webhook_max_inflight: int
    webhook_max_body_bytes: int
    webhook_handler_timeout_seconds: int
    webhook_registration_retries: int
    webhook_watchdog_enabled: bool
    webhook_watchdog_interval_seconds: int
    memory_pressure_limit_pct: int
    bot_default_max_inflight: int
    bot_default_rate_per_minute: int
    bot_default_burst: int
    bot_failure_threshold: int
    bot_failure_window_seconds: int
    bot_failure_cooldown_seconds: int
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
    deploy_require_2fa: bool
    deploy_totp_secret: str | None
    deploy_2fa_session_seconds: int
    deploy_admin_rate_per_minute: int
    deploy_admin_rate_burst: int
    audit_log_path: Path
    audit_hmac_key: str | None
    audit_max_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=_int("PORT", 10000, 1, 65535),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            admin_token=os.getenv("ADMIN_TOKEN", "").strip() or None,
            admin_api_enabled=_bool("ADMIN_API_ENABLED", False),
            public_status_details=_bool("PUBLIC_STATUS_DETAILS", False),
            metrics_public=_bool("METRICS_PUBLIC", False),
            public_base_url=_public_base_url(),
            platform=_platform_name(),
            control_plane_only=_bool("CONTROL_PLANE_ONLY", False),
            max_bots_per_runtime=_int("MAX_BOTS_PER_RUNTIME", 0, 0, 1000),
            bots_json=os.getenv("BOTS_JSON", "[]"),
            auto_register_webhooks=_bool("AUTO_REGISTER_WEBHOOKS", False),
            webhook_secret_key=os.getenv("WEBHOOK_SECRET_KEY", "").strip() or None,
            telegram_max_connections=_int("TELEGRAM_MAX_CONNECTIONS", 10, 1, 100),
            webhook_max_inflight=_int("WEBHOOK_MAX_INFLIGHT", 24, 1, 256),
            webhook_max_body_bytes=_int("WEBHOOK_MAX_BODY_BYTES", 1_000_000, 4_096, 10_000_000),
            webhook_handler_timeout_seconds=_int("WEBHOOK_HANDLER_TIMEOUT_SECONDS", 10, 1, 120),
            webhook_registration_retries=_int("WEBHOOK_REGISTRATION_RETRIES", 3, 1, 10),
            webhook_watchdog_enabled=_bool("WEBHOOK_WATCHDOG_ENABLED", True),
            webhook_watchdog_interval_seconds=_int("WEBHOOK_WATCHDOG_INTERVAL_SECONDS", 300, 60, 3600),
            memory_pressure_limit_pct=_int("MEMORY_PRESSURE_LIMIT_PCT", 90, 50, 99),
            bot_default_max_inflight=_int("BOT_DEFAULT_MAX_INFLIGHT", 8, 1, 64),
            bot_default_rate_per_minute=_int("BOT_DEFAULT_RATE_PER_MINUTE", 600, 30, 100_000),
            bot_default_burst=_int("BOT_DEFAULT_BURST", 50, 1, 5_000),
            bot_failure_threshold=_int("BOT_FAILURE_THRESHOLD", 5, 2, 100),
            bot_failure_window_seconds=_int("BOT_FAILURE_WINDOW_SECONDS", 60, 10, 3600),
            bot_failure_cooldown_seconds=_int("BOT_FAILURE_COOLDOWN_SECONDS", 30, 5, 3600),
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
            deploy_require_2fa=_bool("DEPLOY_REQUIRE_2FA", False),
            deploy_totp_secret=os.getenv("DEPLOY_TOTP_SECRET", "").strip() or None,
            deploy_2fa_session_seconds=_int("DEPLOY_2FA_SESSION_SECONDS", 300, 30, 3600),
            deploy_admin_rate_per_minute=_int("DEPLOY_ADMIN_RATE_PER_MINUTE", 60, 10, 1000),
            deploy_admin_rate_burst=_int("DEPLOY_ADMIN_RATE_BURST", 15, 2, 100),
            audit_log_path=Path(os.getenv("AUDIT_LOG_PATH", "/workspace/titanbox-data/audit/audit.jsonl")),
            audit_hmac_key=os.getenv("AUDIT_HMAC_KEY", "").strip() or None,
            audit_max_bytes=_int("AUDIT_MAX_BYTES", 5_000_000, 100_000, 100_000_000),
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

    def known_secret_values(self) -> list[str]:
        values = [
            self.admin_token,
            self.webhook_secret_key,
            self.terminal_password,
            self.deploy_totp_secret,
            self.audit_hmac_key,
        ]
        for descriptor in self.bot_descriptors():
            if not isinstance(descriptor, dict):
                continue
            for key in ("token_env", "secret_env"):
                env_name = str(descriptor.get(key, "")).strip()
                if env_name:
                    values.append(os.getenv(env_name, "").strip() or None)
        return [value for value in values if value]

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
        if self.deploy_admin_configured() and not self.deploy_require_2fa:
            warnings.append("Deploy Admin 2FA is disabled. Enable DEPLOY_REQUIRE_2FA=true and set DEPLOY_TOTP_SECRET before production use.")
        if self.deploy_admin_configured() and not self.audit_hmac_key:
            warnings.append("AUDIT_HMAC_KEY is missing. Audit records are hash-chained but not keyed against forgery.")
        if self.deploy_require_2fa and not self.deploy_totp_secret:
            warnings.append("Deploy Admin 2FA is REQUIRED but DEPLOY_TOTP_SECRET is missing; destructive commands are intentionally blocked.")
        if len(descriptors) > 1:
            warnings.append("Multiple Ultra Mode bots share one Python process. This is efficient but not a strict security boundary; use separate services for hard isolation.")
        if self.control_plane_only:
            warnings.append("CONTROL_PLANE_ONLY is enabled: this runtime is reserved for Deploy Admin/control-plane components.")
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

        if self.admin_api_enabled and not self.admin_token:
            raise ValueError("ADMIN_TOKEN is required when ADMIN_API_ENABLED=true")

        if self.deploy_totp_secret:
            normalized = "".join(self.deploy_totp_secret.split()).upper()
            if len(normalized.rstrip("=")) < 16 or not _BASE32_RE.fullmatch(normalized):
                raise ValueError("DEPLOY_TOTP_SECRET must be a Base32 secret with at least 16 characters")

        descriptors = self.bot_descriptors()
        if self.max_bots_per_runtime and len(descriptors) > self.max_bots_per_runtime:
            raise ValueError(
                f"BOTS_JSON configures {len(descriptors)} bots but MAX_BOTS_PER_RUNTIME={self.max_bots_per_runtime}. "
                "Deploy extra bots as separate services for hard isolation or explicitly raise the limit."
            )
        if self.control_plane_only:
            for descriptor in descriptors:
                if not isinstance(descriptor, dict) or "deploy_admin" not in str(descriptor.get("plugin", "")):
                    raise ValueError(
                        "CONTROL_PLANE_ONLY=true only permits the Deploy Admin plugin. "
                        "Run student/public bots in a separate service/container."
                    )
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
