from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, Request, status

from .security import FailureCircuit, SecretRedactor, TokenBucket
from .settings import Settings
from .system_metrics import memory_pressure_pct

log = logging.getLogger("titanbox.telegram")


@dataclass(frozen=True, slots=True)
class PluginServices:
    # NOTE: Ultra Mode plugins share a Python process. This service object is designed for
    # convenience/least-privilege-by-convention, not as a hard security boundary.
    settings: Settings
    runner: Any | None = None
    infrastructure: Any | None = None
    bot_context: Any | None = None


class Plugin(Protocol):
    async def handle(self, update: dict[str, Any], bot: "BotContext") -> None: ...


@dataclass(frozen=True, slots=True)
class BotSpec:
    name: str
    token: str
    secret: str
    plugin_path: str
    max_inflight: int
    rate_per_minute: int
    burst: int
    handler_timeout_seconds: int
    failure_threshold: int
    failure_window_seconds: int
    failure_cooldown_seconds: int
    allowed_updates: tuple[str, ...]


@dataclass(slots=True)
class BotRuntimeState:
    name: str
    plugin: str
    loaded: bool = False
    ready: bool = False
    username: str | None = None
    expected_webhook_url: str | None = None
    webhook_url: str | None = None
    pending_update_count: int | None = None
    last_webhook_error: str | None = None
    startup_error: str | None = None
    active_handlers: int = 0
    total_handled: int = 0
    total_rejected: int = 0
    last_update_at: float | None = None
    circuit_open: bool = False
    circuit_retry_after_seconds: int = 0
    recent_failures: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "loaded": self.loaded,
            "ready": self.ready,
            "username": self.username,
            "active_handlers": self.active_handlers,
            "circuit_open": self.circuit_open,
        }

    def detail(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "plugin": self.plugin,
            "expected_webhook_url": self.expected_webhook_url,
            "webhook_url": self.webhook_url,
            "pending_update_count": self.pending_update_count,
            "last_webhook_error": self.last_webhook_error,
            "startup_error": self.startup_error,
            "total_handled": self.total_handled,
            "total_rejected": self.total_rejected,
            "last_update_at": self.last_update_at,
            "circuit_retry_after_seconds": self.circuit_retry_after_seconds,
            "recent_failures": self.recent_failures,
        }


class UpdateDeduplicator:
    """Two-phase bounded dedupe: never marks a failed update as completed."""

    def __init__(self, max_items: int = 2048, ttl_seconds: int = 3600):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._completed: OrderedDict[int, float] = OrderedDict()
        self._inflight: set[int] = set()
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        while self._completed:
            first_id, ts = next(iter(self._completed.items()))
            if now - ts <= self.ttl_seconds:
                break
            self._completed.pop(first_id, None)
        while len(self._completed) > self.max_items:
            self._completed.popitem(last=False)

    async def begin(self, update_id: int) -> str:
        now = time.monotonic()
        async with self._lock:
            self._prune(now)
            if update_id in self._completed:
                self._completed.move_to_end(update_id)
                return "completed"
            if update_id in self._inflight:
                return "inflight"
            self._inflight.add(update_id)
            return "new"

    async def complete(self, update_id: int) -> None:
        async with self._lock:
            self._inflight.discard(update_id)
            self._completed[update_id] = time.monotonic()
            self._completed.move_to_end(update_id)
            self._prune(time.monotonic())

    async def fail(self, update_id: int) -> None:
        async with self._lock:
            self._inflight.discard(update_id)


class BotContext:
    def __init__(self, name: str, token: str, client: httpx.AsyncClient):
        self.name = name
        self._token = token
        self._client = client

    async def api(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._client.post(
                f"https://api.telegram.org/bot{self._token}/{method}",
                json=payload or {},
                timeout=20.0,
            )
        except httpx.RequestError as exc:
            # Never stringify the Request object here: its URL contains the bot token.
            raise RuntimeError(f"Telegram network error during {method}: {type(exc).__name__}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Telegram API {method} returned HTTP {response.status_code} with invalid JSON") from exc
        if response.is_error or not data.get("ok"):
            description = str(data.get("description") or "unknown error")
            raise RuntimeError(f"Telegram API {method} failed HTTP {response.status_code}: {description}")
        return data.get("result")

    async def send_message(self, chat_id: int | str, text: str, **extra: Any) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        payload.update(extra)
        return await self.api("sendMessage", payload)

    async def get_me(self) -> dict[str, Any]:
        result = await self.api("getMe")
        if not isinstance(result, dict):
            raise RuntimeError("Telegram getMe returned an invalid response")
        return result

    async def get_webhook_info(self) -> dict[str, Any]:
        result = await self.api("getWebhookInfo")
        if not isinstance(result, dict):
            raise RuntimeError("Telegram getWebhookInfo returned an invalid response")
        return result

    async def get_file(self, file_id: str) -> dict[str, Any]:
        result = await self.api("getFile", {"file_id": file_id})
        if not isinstance(result, dict) or not result.get("file_path"):
            raise RuntimeError("Telegram did not return a downloadable file path")
        return result

    async def download_file(self, file_id: str, destination: Path, max_bytes: int) -> int:
        info = await self.get_file(file_id)
        declared = info.get("file_size")
        if isinstance(declared, int) and declared > max_bytes:
            raise ValueError("Telegram file exceeds configured upload limit")
        file_path = str(info["file_path"])
        url = f"https://api.telegram.org/file/bot{self._token}/{file_path}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            async with self._client.stream("GET", url, timeout=60.0) as response:
                if response.is_error:
                    # Do not raise HTTPStatusError because it embeds the token-bearing URL.
                    raise RuntimeError(f"Telegram file download failed HTTP {response.status_code}")
                length = response.headers.get("content-length")
                if length:
                    try:
                        if int(length) > max_bytes:
                            raise ValueError("Telegram file exceeds configured upload limit")
                    except ValueError:
                        # Invalid Content-Length must not disable streaming size enforcement.
                        if length.isdigit():
                            raise
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        written += len(chunk)
                        if written > max_bytes:
                            raise ValueError("Telegram file exceeds configured upload limit")
                        handle.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return written


@dataclass(slots=True)
class BotControl:
    semaphore: asyncio.Semaphore
    limiter: TokenBucket
    circuit: FailureCircuit


class TelegramHub:
    def __init__(self, settings: Settings, runner: Any | None = None, infrastructure: Any | None = None):
        self.settings = settings
        self.runner = runner
        self.infrastructure = infrastructure
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8, keepalive_expiry=20.0),
            headers={"User-Agent": "TitanBox/1.0"},
        )
        self.bots: dict[str, BotSpec] = {}
        self.plugins: dict[str, Plugin] = {}
        self.dedup: dict[str, UpdateDeduplicator] = {}
        self.runtime: dict[str, BotRuntimeState] = {}
        self.controls: dict[str, BotControl] = {}
        self.configured_count = 0
        self._global_slots = asyncio.Semaphore(settings.webhook_max_inflight)
        self._watchdog_task: asyncio.Task[None] | None = None
        self._initial_register_task: asyncio.Task[list[dict[str, Any]]] | None = None
        self.active_handlers = 0
        self.total_handled = 0
        self.total_rejected = 0
        self.redactor = SecretRedactor(settings.known_secret_values())

    @staticmethod
    def _safe_bot_name(name: str) -> str:
        if not name or len(name) > 48 or not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid bot name: {name!r}")
        return name

    @staticmethod
    def _load_plugin(path: str) -> Plugin:
        module_name, sep, attr = path.partition(":")
        if not sep:
            raise ValueError(f"plugin path must look like module:Class, got {path!r}")
        module = importlib.import_module(module_name)
        cls = getattr(module, attr)
        return cls()

    @staticmethod
    def _allowed_updates(raw: dict[str, Any]) -> tuple[str, ...]:
        allowed_names = {
            "message", "edited_message", "channel_post", "edited_channel_post",
            "business_connection", "business_message", "edited_business_message",
            "deleted_business_messages", "message_reaction", "message_reaction_count",
            "inline_query", "chosen_inline_result", "callback_query", "shipping_query",
            "pre_checkout_query", "purchased_paid_media", "poll", "poll_answer",
            "my_chat_member", "chat_member", "chat_join_request", "chat_boost",
            "removed_chat_boost",
        }
        value = raw.get("allowed_updates", ["message", "callback_query"])
        if not isinstance(value, list) or not value or len(value) > len(allowed_names):
            raise ValueError("allowed_updates must be a non-empty JSON array")
        result: list[str] = []
        for item in value:
            name = str(item).strip()
            if name not in allowed_names:
                raise ValueError(f"unsupported Telegram update type: {name!r}")
            if name not in result:
                result.append(name)
        return tuple(result)

    @staticmethod
    def _limit_value(raw: dict[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
        limits = raw.get("limits")
        source = limits if isinstance(limits, dict) else raw
        value = source.get(name, default)
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bot limit {name} must be an integer") from exc
        if parsed < minimum or parsed > maximum:
            raise ValueError(f"bot limit {name} must be between {minimum} and {maximum}")
        return parsed

    def _derive_secret(self, name: str, token: str, secret_env: str) -> str:
        if secret_env:
            explicit = os.getenv(secret_env, "").strip()
            if explicit:
                return explicit
        key = (self.settings.webhook_secret_key or token).encode("utf-8")
        digest = hmac.new(key, f"titanbox:{name}:webhook".encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _clean_error(self, exc: Exception) -> str:
        text = self.redactor.redact(str(exc).replace("\n", " ").strip())
        if len(text) > 300:
            text = text[:297] + "..."
        return f"{type(exc).__name__}: {text}"

    def _sync_circuit_state(self, name: str) -> None:
        control = self.controls.get(name)
        state = self.runtime.get(name)
        if control is None or state is None:
            return
        state.circuit_retry_after_seconds = control.circuit.retry_after()
        state.circuit_open = state.circuit_retry_after_seconds > 0
        state.recent_failures = control.circuit.recent_failures()

    async def start(self) -> None:
        descriptors = self.settings.bot_descriptors()
        self.configured_count = len(descriptors)
        for index, raw in enumerate(descriptors):
            plugin_path = "unknown"
            state_name = f"invalid-{index + 1}"
            try:
                if not isinstance(raw, dict):
                    raise ValueError("each BOTS_JSON item must be an object")
                state_name = self._safe_bot_name(str(raw.get("name", "")).strip())
                token_env = str(raw.get("token_env", "")).strip()
                secret_env = str(raw.get("secret_env", "")).strip()
                plugin_path = str(raw.get("plugin", "titanbox.plugins.default:DefaultPlugin"))
                state = BotRuntimeState(name=state_name, plugin=plugin_path)
                self.runtime[state_name] = state
                if not token_env:
                    raise ValueError(f"bot {state_name}: token_env is required")
                token = os.getenv(token_env, "").strip()
                if not token:
                    raise ValueError(f"bot {state_name}: missing environment secret {token_env}")
                secret = self._derive_secret(state_name, token, secret_env)
                if len(secret) > 256 or any(
                    ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for ch in secret
                ):
                    raise ValueError(f"bot {state_name}: webhook secret contains characters Telegram does not allow")
                if state_name in self.bots:
                    raise ValueError(f"duplicate bot name: {state_name}")

                spec = BotSpec(
                    name=state_name,
                    token=token,
                    secret=secret,
                    plugin_path=plugin_path,
                    max_inflight=self._limit_value(raw, "max_inflight", self.settings.bot_default_max_inflight, 1, 64),
                    rate_per_minute=self._limit_value(raw, "rate_per_minute", self.settings.bot_default_rate_per_minute, 10, 100_000),
                    burst=self._limit_value(raw, "burst", self.settings.bot_default_burst, 1, 5_000),
                    handler_timeout_seconds=self._limit_value(
                        raw,
                        "handler_timeout_seconds",
                        self.settings.webhook_handler_timeout_seconds,
                        1,
                        120,
                    ),
                    failure_threshold=self._limit_value(raw, "failure_threshold", self.settings.bot_failure_threshold, 2, 100),
                    failure_window_seconds=self._limit_value(
                        raw, "failure_window_seconds", self.settings.bot_failure_window_seconds, 10, 3600
                    ),
                    failure_cooldown_seconds=self._limit_value(
                        raw, "failure_cooldown_seconds", self.settings.bot_failure_cooldown_seconds, 5, 3600
                    ),
                    allowed_updates=self._allowed_updates(raw),
                )
                self.bots[state_name] = spec
                self.controls[state_name] = BotControl(
                    semaphore=asyncio.Semaphore(spec.max_inflight),
                    limiter=TokenBucket(spec.rate_per_minute, spec.burst),
                    circuit=FailureCircuit(
                        spec.failure_threshold,
                        float(spec.failure_window_seconds),
                        float(spec.failure_cooldown_seconds),
                    ),
                )
                plugin = self._load_plugin(plugin_path)
                service_bot_context = BotContext(spec.name, spec.token, self.client)
                binder = getattr(plugin, "bind_services", None)
                if callable(binder):
                    binder(
                        PluginServices(
                            settings=self.settings,
                            runner=self.runner,
                            infrastructure=self.infrastructure,
                            bot_context=service_bot_context,
                        )
                    )
                starter = getattr(plugin, "start", None)
                if callable(starter):
                    started = starter()
                    if started is not None:
                        await started
                self.plugins[state_name] = plugin
                self.dedup[state_name] = UpdateDeduplicator()
                state.loaded = True
                state.ready = not self.settings.auto_register_webhooks
                if self.settings.public_base_url:
                    state.expected_webhook_url = f"{self.settings.public_base_url}/telegram/{state_name}"
            except Exception as exc:
                state = self.runtime.setdefault(state_name, BotRuntimeState(name=state_name, plugin=plugin_path))
                state.startup_error = self._clean_error(exc)
                log.error("bot configuration failed bot=%s error=%s", state_name, state.startup_error)

        # Refresh redaction after all token env vars have been resolved.
        self.redactor.refresh(self.settings.known_secret_values())
        if self.settings.auto_register_webhooks:
            if self.settings.webhook_register_background:
                # Cold-start optimization: once tokens/plugins are loaded, the public webhook
                # can already accept Telegram's previously-registered URL while registration
                # verification proceeds in the background.
                self._initial_register_task = asyncio.create_task(
                    self.register_all_webhooks(),
                    name="telegram-initial-webhook-register",
                )
            else:
                await self.register_all_webhooks()
        if (
            self.settings.auto_register_webhooks
            and self.settings.webhook_watchdog_enabled
            and self.bots
        ):
            self._watchdog_task = asyncio.create_task(self._webhook_watchdog(), name="telegram-webhook-watchdog")

    async def close(self) -> None:
        if self._initial_register_task:
            self._initial_register_task.cancel()
            await asyncio.gather(self._initial_register_task, return_exceptions=True)
            self._initial_register_task = None
        if self._watchdog_task:
            self._watchdog_task.cancel()
            await asyncio.gather(self._watchdog_task, return_exceptions=True)
            self._watchdog_task = None
        for plugin in self.plugins.values():
            closer = getattr(plugin, "close", None)
            if callable(closer):
                result = closer()
                if result is not None:
                    await result
        await self.client.aclose()

    async def _register_one(self, bot: BotSpec) -> dict[str, Any]:
        if not self.settings.public_base_url:
            raise RuntimeError("No public base URL is available")
        url = f"{self.settings.public_base_url}/telegram/{bot.name}"
        ctx = BotContext(bot.name, bot.token, self.client)
        me = await ctx.get_me()
        await ctx.api(
            "setWebhook",
            {
                "url": url,
                "secret_token": bot.secret,
                "max_connections": self.settings.telegram_max_connections,
                "allowed_updates": list(bot.allowed_updates),
            },
        )
        info = await ctx.get_webhook_info()
        if str(info.get("url") or "") != url:
            raise RuntimeError(f"Telegram webhook verification mismatch: expected {url!r}, got {info.get('url')!r}")
        state = self.runtime[bot.name]
        state.username = str(me.get("username") or "") or None
        state.webhook_url = str(info.get("url") or "") or None
        state.pending_update_count = int(info.get("pending_update_count") or 0)
        last_error_message = str(info.get("last_error_message") or "").strip()
        state.last_webhook_error = last_error_message or None
        state.startup_error = None
        state.ready = True
        log.info("registered Telegram webhook bot=%s username=%s url=%s", bot.name, state.username, url)
        return state.detail()

    async def register_all_webhooks(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for bot in list(self.bots.values()):
            state = self.runtime[bot.name]
            state.ready = False
            last_exc: Exception | None = None
            for attempt in range(1, self.settings.webhook_registration_retries + 1):
                try:
                    results.append(await self._register_one(bot))
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    state.startup_error = self._clean_error(exc)
                    log.warning(
                        "webhook registration failed bot=%s attempt=%s/%s error=%s",
                        bot.name,
                        attempt,
                        self.settings.webhook_registration_retries,
                        state.startup_error,
                    )
                    if attempt < self.settings.webhook_registration_retries:
                        await asyncio.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))
            if last_exc is not None:
                results.append(state.detail())
        return results

    async def _refresh_one(self, name: str) -> dict[str, Any]:
        bot = self.bots.get(name)
        if bot is None:
            raise ValueError("Unknown bot")
        state = self.runtime[name]
        ctx = BotContext(bot.name, bot.token, self.client)
        me = await ctx.get_me()
        info = await ctx.get_webhook_info()
        state.username = str(me.get("username") or "") or None
        state.webhook_url = str(info.get("url") or "") or None
        state.pending_update_count = int(info.get("pending_update_count") or 0)
        state.last_webhook_error = str(info.get("last_error_message") or "").strip() or None
        expected = state.expected_webhook_url
        state.ready = state.loaded and (not self.settings.auto_register_webhooks or state.webhook_url == expected)
        state.startup_error = None
        return state.detail()

    async def refresh_webhook_info(self, name: str) -> dict[str, Any]:
        if name not in self.bots:
            raise ValueError("Unknown bot")
        state = self.runtime[name]
        try:
            return await self._refresh_one(name)
        except Exception as exc:
            state.startup_error = self._clean_error(exc)
            state.ready = False
            return state.detail()

    async def _webhook_watchdog(self) -> None:
        interval = self.settings.webhook_watchdog_interval_seconds
        while True:
            try:
                await asyncio.sleep(interval)
                for name, bot in list(self.bots.items()):
                    try:
                        state = self.runtime[name]
                        await self._refresh_one(name)
                        if state.webhook_url != state.expected_webhook_url:
                            log.warning(
                                "webhook watchdog repairing bot=%s actual=%s expected=%s",
                                name,
                                state.webhook_url,
                                state.expected_webhook_url,
                            )
                            await self._register_one(bot)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        state = self.runtime[name]
                        state.ready = False
                        state.startup_error = self._clean_error(exc)
                        log.warning("webhook watchdog check failed bot=%s error=%s", name, state.startup_error)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("webhook watchdog loop failed")

    async def _acquire_slot(self, semaphore: asyncio.Semaphore, timeout: float = 0.1) -> bool:
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def handle(self, name: str, request: Request) -> dict[str, bool]:
        bot = self.bots.get(name)
        if bot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown bot")
        state = self.runtime[name]
        control = self.controls[name]
        presented = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(presented.encode(), bot.secret.encode()):
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        content_type = request.headers.get("content-type", "")
        if content_type and "application/json" not in content_type.lower():
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="JSON required")
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.settings.webhook_max_body_bytes:
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Webhook body too large")
        # Stream with a hard cap so a chunked request cannot force Starlette to buffer an
        # arbitrarily large body before our size check. Telegram updates are tiny; this is
        # primarily a defense against direct Internet abuse of the public webhook endpoint.
        body_buffer = bytearray()
        async for chunk in request.stream():
            body_buffer.extend(chunk)
            if len(body_buffer) > self.settings.webhook_max_body_bytes:
                state.total_rejected += 1
                self.total_rejected += 1
                raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Webhook body too large")
        body = bytes(body_buffer)
        try:
            update = json.loads(body)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
        if not isinstance(update, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid update")
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing update_id")

        pressure = memory_pressure_pct()
        if pressure is not None and pressure >= self.settings.memory_pressure_limit_pct:
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory pressure; retry later",
                headers={"Retry-After": "2"},
            )

        self._sync_circuit_state(name)
        if control.circuit.is_open():
            retry_after = control.circuit.retry_after()
            state.total_rejected += 1
            self.total_rejected += 1
            self._sync_circuit_state(name)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bot circuit open; retry later",
                headers={"Retry-After": str(retry_after)},
            )

        if not await control.limiter.allow():
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bot rate limit exceeded",
                headers={"Retry-After": "1"},
            )

        disposition = await self.dedup[name].begin(update_id)
        if disposition == "completed":
            return {"ok": True}
        if disposition == "inflight":
            # Never acknowledge an in-flight duplicate as successful. If the original request
            # later fails, a premature 200 here could cause Telegram to consider the update
            # delivered and the event would be lost. Ask Telegram to retry instead.
            state.total_rejected += 1
            self.total_rejected += 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Update already in progress; retry later",
                headers={"Retry-After": "1"},
            )

        global_acquired = False
        bot_acquired = False
        try:
            global_acquired = await self._acquire_slot(self._global_slots)
            if not global_acquired:
                await self.dedup[name].fail(update_id)
                state.total_rejected += 1
                self.total_rejected += 1
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Runtime busy; retry later",
                    headers={"Retry-After": "1"},
                )
            bot_acquired = await self._acquire_slot(control.semaphore)
            if not bot_acquired:
                await self.dedup[name].fail(update_id)
                state.total_rejected += 1
                self.total_rejected += 1
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Bot busy; retry later",
                    headers={"Retry-After": "1"},
                )

            self.active_handlers += 1
            state.active_handlers += 1
            state.last_update_at = time.time()
            ctx = BotContext(bot.name, bot.token, self.client)
            try:
                await asyncio.wait_for(
                    self.plugins[name].handle(update, ctx),
                    timeout=bot.handler_timeout_seconds,
                )
            except TimeoutError as exc:
                control.circuit.record_failure()
                self._sync_circuit_state(name)
                await self.dedup[name].fail(update_id)
                state.total_rejected += 1
                self.total_rejected += 1
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Handler timeout; retry later",
                    headers={"Retry-After": "2"},
                ) from exc
            except Exception as exc:
                control.circuit.record_failure()
                self._sync_circuit_state(name)
                await self.dedup[name].fail(update_id)
                state.total_rejected += 1
                self.total_rejected += 1
                log.exception("bot handler failed bot=%s update_id=%s", name, update_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Handler failed; retry later",
                    headers={"Retry-After": "2"},
                ) from exc
            else:
                control.circuit.record_success()
                self._sync_circuit_state(name)
                await self.dedup[name].complete(update_id)
                state.total_handled += 1
                self.total_handled += 1
                return {"ok": True}
        finally:
            if bot_acquired:
                control.semaphore.release()
                state.active_handlers = max(0, state.active_handlers - 1)
            if global_acquired:
                self._global_slots.release()
                self.active_handlers = max(0, self.active_handlers - 1)

    def all_ready(self) -> bool:
        if self.configured_count == 0:
            return True
        if len(self.runtime) != self.configured_count:
            return False
        return all(state.ready for state in self.runtime.values())

    def public_status(self, detailed: bool = False) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name in sorted(self.runtime):
            self._sync_circuit_state(name)
            state = self.runtime[name]
            result.append(state.detail() if detailed else state.summary())
        return result
