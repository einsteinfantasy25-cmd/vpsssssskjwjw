import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from titanbox.settings import Settings
from titanbox.telegram import TelegramHub, UpdateDeduplicator


async def test_deduplicator_two_phase():
    d = UpdateDeduplicator(max_items=2, ttl_seconds=100)
    assert await d.begin(1) == "new"
    assert await d.begin(1) == "inflight"
    await d.fail(1)
    assert await d.begin(1) == "new"
    await d.complete(1)
    assert await d.begin(1) == "completed"


def test_webhook_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("BOT_A_TOKEN", "1:abc")
    monkeypatch.setenv("BOT_A_SECRET", "Valid_secret_123")
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "a",
        "token_env": "BOT_A_TOKEN",
        "secret_env": "BOT_A_SECRET",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    settings = Settings.from_env()
    hub = TelegramHub(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await hub.start()
        try:
            yield
        finally:
            await hub.close()

    app = FastAPI(lifespan=lifespan)

    @app.post("/telegram/{name}")
    async def hook(name: str, request: Request):
        return await hub.handle(name, request)

    with TestClient(app) as client:
        response = client.post("/telegram/a", json={"update_id": 1})
        assert response.status_code == 403


def test_failed_update_can_be_retried(monkeypatch):
    class FlakyPlugin:
        def __init__(self):
            self.calls = 0

        async def handle(self, update, bot):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("first attempt fails")

    monkeypatch.setenv("BOT_B_TOKEN", "2:def")
    monkeypatch.setenv("BOT_B_SECRET", "Retry_secret_123")
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "b",
        "token_env": "BOT_B_TOKEN",
        "secret_env": "BOT_B_SECRET",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    monkeypatch.setenv("MEMORY_PRESSURE_LIMIT_PCT", "99")
    settings = Settings.from_env()
    hub = TelegramHub(settings)
    flaky = FlakyPlugin()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await hub.start()
        hub.plugins["b"] = flaky
        try:
            yield
        finally:
            await hub.close()

    app = FastAPI(lifespan=lifespan)

    @app.post("/telegram/{name}")
    async def hook(name: str, request: Request):
        return await hub.handle(name, request)

    headers = {"X-Telegram-Bot-Api-Secret-Token": "Retry_secret_123"}
    with TestClient(app) as client:
        first = client.post("/telegram/b", headers=headers, json={"update_id": 99})
        second = client.post("/telegram/b", headers=headers, json={"update_id": 99})
        third = client.post("/telegram/b", headers=headers, json={"update_id": 99})
        assert first.status_code == 503
        assert second.status_code == 200
        assert third.status_code == 200
        assert flaky.calls == 2


def test_missing_token_does_not_crash_entire_hub(monkeypatch):
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "missing",
        "token_env": "DOES_NOT_EXIST",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    settings = Settings.from_env()
    hub = TelegramHub(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await hub.start()
        try:
            yield
        finally:
            await hub.close()

    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        assert hub.configured_count == 1
        assert len(hub.bots) == 0
        assert hub.runtime["missing"].startup_error
        assert not hub.all_ready()


def test_secret_can_be_derived_without_secret_env(monkeypatch):
    monkeypatch.setenv("BOT_DERIVED_TOKEN", "123456:abcdef")
    monkeypatch.setenv("WEBHOOK_SECRET_KEY", "internal-key-that-can-contain-anything==")
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "derived",
        "token_env": "BOT_DERIVED_TOKEN",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    settings = Settings.from_env()
    hub = TelegramHub(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await hub.start()
        try:
            yield
        finally:
            await hub.close()

    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        secret = hub.bots["derived"].secret
        assert secret
        assert all(ch.isalnum() or ch in "_-" for ch in secret)


async def test_auto_register_webhook_and_verify(monkeypatch):
    import httpx

    monkeypatch.setenv("BOT_AUTO_TOKEN", "123456:abcdef")
    monkeypatch.setenv("WEBHOOK_SECRET_KEY", "render-generated-internal-key==")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.onrender.com")
    monkeypatch.setenv("AUTO_REGISTER_WEBHOOKS", "true")
    monkeypatch.setenv("WEBHOOK_REGISTRATION_RETRIES", "1")
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "auto",
        "token_env": "BOT_AUTO_TOKEN",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    settings = Settings.from_env()
    settings.validate()
    hub = TelegramHub(settings)
    await hub.client.aclose()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": 1, "username": "AutoBot"}})
        if method == "setWebhook":
            payload = json.loads(request.content.decode())
            captured.update(payload)
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {
                "url": "https://example.onrender.com/telegram/auto",
                "pending_update_count": 0,
            }})
        raise AssertionError(method)

    hub.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await hub.start()
        assert hub.all_ready()
        assert hub.runtime["auto"].username == "AutoBot"
        assert captured["url"] == "https://example.onrender.com/telegram/auto"
        assert captured["secret_token"] == hub.bots["auto"].secret
    finally:
        await hub.close()


async def test_invalid_token_error_never_leaks_token(monkeypatch):
    import httpx

    secret_token = "999999:SUPER_SECRET_TOKEN_VALUE"
    monkeypatch.setenv("BOT_BAD_TOKEN", secret_token)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.onrender.com")
    monkeypatch.setenv("AUTO_REGISTER_WEBHOOKS", "true")
    monkeypatch.setenv("WEBHOOK_REGISTRATION_RETRIES", "1")
    monkeypatch.setenv("BOTS_JSON", json.dumps([{
        "name": "bad",
        "token_env": "BOT_BAD_TOKEN",
        "plugin": "titanbox.plugins.default:DefaultPlugin",
    }]))
    settings = Settings.from_env()
    hub = TelegramHub(settings)
    await hub.client.aclose()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})

    hub.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await hub.start()
        error = hub.runtime["bad"].startup_error or ""
        assert secret_token not in error
        assert "Unauthorized" in error
        assert not hub.all_ready()
    finally:
        await hub.close()
