import asyncio
from pathlib import Path

import pytest

from titanbox.plugins.deploy_admin import DeployAdminPlugin
from titanbox.settings import Settings
from titanbox.telegram import PluginServices


class FakeBot:
    def __init__(self, source: Path | None = None):
        self.source = source
        self.messages: list[str] = []
        self.name = "deploy-admin"

    async def send_message(self, chat_id, text, **extra):
        self.messages.append(text)
        return {"chat_id": chat_id}

    async def download_file(self, file_id: str, destination: Path, max_bytes: int):
        assert self.source is not None
        data = self.source.read_bytes()
        assert len(data) <= max_bytes
        destination.write_bytes(data)
        return len(data)

    async def get_me(self):
        return {"id": 1, "username": "DeployAdminTestBot"}

    async def get_webhook_info(self):
        return {"url": "https://example.onrender.com/telegram/deploy-admin", "pending_update_count": 0}


def make_settings(monkeypatch, root: Path) -> Settings:
    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("DEPLOY_ROOT", str(root))
    monkeypatch.setenv("DEPLOY_ADMIN_TELEGRAM_IDS", "123")
    return Settings.from_env()


@pytest.mark.asyncio
async def test_unauthorized_user_gets_clear_denial(monkeypatch, tmp_path: Path):
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path)))
    bot = FakeBot()
    update = {"message": {"from": {"id": 999}, "chat": {"id": 1}, "text": "/help"}}
    await plugin.handle(update, bot)
    assert bot.messages
    assert "999" in bot.messages[-1]
    assert "غير مصرح" in bot.messages[-1]


@pytest.mark.asyncio
async def test_help_for_admin(monkeypatch, tmp_path: Path):
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path)))
    bot = FakeBot()
    update = {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": "/help"}}
    await plugin.handle(update, bot)
    assert bot.messages and "TitanBox Deploy Admin" in bot.messages[-1]

@pytest.mark.asyncio
async def test_smart_single_file_update(monkeypatch, tmp_path: Path):
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path / "data")))
    assert plugin.manager is not None

    import zipfile

    archive = tmp_path / "project.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.py", "VALUE = 1\n")
    await plugin.manager.deploy_zip("mybot", archive)

    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 9\n")
    bot = FakeBot(replacement)

    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": "/use mybot"}},
        bot,
    )
    await plugin.handle(
        {
            "message": {
                "from": {"id": 123},
                "chat": {"id": 1},
                "document": {"file_id": "abc", "file_name": "main.py", "file_size": replacement.stat().st_size},
            }
        },
        bot,
    )
    if plugin._tasks:
        await asyncio.gather(*list(plugin._tasks))

    current = plugin.manager.current_release_path("mybot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 9\n"
    assert any("تم تحديث main.py" in text for text in bot.messages)


@pytest.mark.asyncio
async def test_unauthorized_start_reveals_own_numeric_id(monkeypatch, tmp_path: Path):
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path)))
    bot = FakeBot()
    await plugin.handle(
        {"message": {"from": {"id": 777001}, "chat": {"id": 1}, "text": "/start"}},
        bot,
    )
    assert any("777001" in text and "DEPLOY_ADMIN_TELEGRAM_IDS" in text for text in bot.messages)


@pytest.mark.asyncio
async def test_admin_diag_reports_webhook(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.onrender.com")
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path)))
    bot = FakeBot()
    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": "/diag"}},
        bot,
    )
    assert any("DeployAdminTestBot" in text and "Pending updates: 0" in text for text in bot.messages)
