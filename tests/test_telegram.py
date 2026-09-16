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
