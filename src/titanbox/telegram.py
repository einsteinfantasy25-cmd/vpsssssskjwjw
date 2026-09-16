from __future__ import annotations

import asyncio
import hmac
import importlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, Request, status

from .settings import Settings
from .system_metrics import memory_pressure_pct

log = logging.getLogger("titanbox.telegram")


@dataclass(frozen=True, slots=True)
class PluginServices:
    settings: Settings
    runner: Any | None = None


class Plugin(Protocol):
    async def handle(self, update: dict[str, Any], bot: "BotContext") -> None: ...


@dataclass(frozen=True, slots=True)
class BotSpec:
    name: str
    token: str
    secret: str
    plugin_path: str


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
        """Return 'new', 'completed', or 'inflight'."""
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
        response = await self._client.post(
            f"https://api.telegram.org/bot{self._token}/{method}",
            json=payload or {},
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data.get('description', 'unknown')}")
        return data.get("result")

    async def send_message(self, chat_id: int | str, text: str, **extra: Any) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        payload.update(extra)
        return await self.api("sendMessage", payload)

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
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise ValueError("Telegram file exceeds configured upload limit")
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


class TelegramHub:
    def __init__(self, settings: Settings, runner: Any | None = None):
        self.settings = settings
        self.runner = runner
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8, keepalive_expiry=20.0),
            headers={"User-Agent": "TitanBox/0.2"},
        )
        self.bots: dict[str, BotSpec] = {}
        self.plugins: dict[str, Plugin] = {}
        self.dedup: dict[str, UpdateDeduplicator] = {}
        self._webhook_slots = asyncio.Semaphore(settings.webhook_max_inflight)
        self.active_handlers = 0
        self.total_handled = 0
        self.total_rejected = 0

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

    async def start(self) -> None:
        for raw in self.settings.bot_descriptors():
            if not isinstance(raw, dict):
                raise ValueError("each BOTS_JSON item must be an object")
            name = self._safe_bot_name(str(raw.get("name", "")).strip())
            token_env = str(raw.get("token_env", "")).strip()
            secret_env = str(raw.get("secret_env", "")).strip()
            plugin_path = str(raw.get("plugin", "titanbox.plugins.default:DefaultPlugin"))
            if not token_env or not secret_env:
                raise ValueError(f"bot {name}: token_env and secret_env are required")
            token = os.getenv(token_env, "").strip()
            secret = os.getenv(secret_env, "").strip()
            if not token or not secret:
                raise ValueError(f"bot {name}: missing environment secret {token_env} or {secret_env}")
            if len(secret) > 256 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for ch in secret):
                raise ValueError(f"bot {name}: webhook secret contains characters Telegram does not allow")
            self.bots[name] = BotSpec(name=name, token=token, secret=secret, plugin_path=plugin_path)
            plugin = self._load_plugin(plugin_path)
            binder = getattr(plugin, "bind_services", None)
            if callable(binder):
                binder(PluginServices(settings=self.settings, runner=self.runner))
            self.plugins[name] = plugin
            self.dedup[name] = UpdateDeduplicator()
        if self.settings.auto_register_webhooks:
            await self.register_all_webhooks()

    async def close(self) -> None:
        for plugin in self.plugins.values():
            closer = getattr(plugin, "close", None)
            if callable(closer):
                result = closer()
                if result is not None:
                    await result
        await self.client.aclose()

    async def register_all_webhooks(self) -> None:
        assert self.settings.public_base_url
        for bot in self.bots.values():
            url = f"{self.settings.public_base_url}/telegram/{bot.name}"
            ctx = BotContext(bot.name, bot.token, self.client)
            await ctx.api(
                "setWebhook",
                {
                    "url": url,
                    "secret_token": bot.secret,
                    "max_connections": self.settings.telegram_max_connections,
                    "allowed_updates": ["message", "edited_message", "callback_query"],
                },
            )
            log.info("registered Telegram webhook bot=%s url=%s", bot.name, url)

    async def handle(self, name: str, request: Request) -> dict[str, bool]:
        bot = self.bots.get(name)
        if bot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown bot")
        presented = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(presented.encode(), bot.secret.encode()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        try:
            update = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing update_id")
        pressure = memory_pressure_pct()
        if pressure is not None and pressure >= self.settings.memory_pressure_limit_pct:
            self.total_rejected += 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory pressure; retry later",
                headers={"Retry-After": "2"},
            )

        disposition = await self.dedup[name].begin(update_id)
        if disposition in {"completed", "inflight"}:
            return {"ok": True}

        acquired = False
        try:
            try:
                await asyncio.wait_for(self._webhook_slots.acquire(), timeout=0.1)
                acquired = True
            except TimeoutError as exc:
                await self.dedup[name].fail(update_id)
                self.total_rejected += 1
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Busy; retry later",
                    headers={"Retry-After": "1"},
                ) from exc

            self.active_handlers += 1
            ctx = BotContext(bot.name, bot.token, self.client)
            try:
                await asyncio.wait_for(
                    self.plugins[name].handle(update, ctx),
                    timeout=self.settings.webhook_handler_timeout_seconds,
                )
            except TimeoutError as exc:
                await self.dedup[name].fail(update_id)
                self.total_rejected += 1
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Handler timeout; retry later",
                    headers={"Retry-After": "2"},
                ) from exc
            except Exception as exc:
                await self.dedup[name].fail(update_id)
                self.total_rejected += 1
                log.exception("bot handler failed bot=%s update_id=%s", name, update_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Handler failed; retry later",
                    headers={"Retry-After": "2"},
                ) from exc
            else:
                await self.dedup[name].complete(update_id)
                self.total_handled += 1
                return {"ok": True}
        finally:
            if acquired:
                self._webhook_slots.release()
                self.active_handlers = max(0, self.active_handlers - 1)

    def public_status(self) -> list[dict[str, str]]:
        return [{"name": bot.name, "plugin": bot.plugin_path} for bot in self.bots.values()]
