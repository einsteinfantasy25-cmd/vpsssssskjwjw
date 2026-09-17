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


def make_settings(monkeypatch, root: Path, *, require_2fa: bool = False, totp_secret: str | None = None) -> Settings:
    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("DEPLOY_ROOT", str(root))
    monkeypatch.setenv("DEPLOY_ADMIN_TELEGRAM_IDS", "123")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(root / "audit" / "audit.jsonl"))
    monkeypatch.setenv("AUDIT_HMAC_KEY", "test-audit-hmac-key")
    monkeypatch.setenv("DEPLOY_REQUIRE_2FA", "true" if require_2fa else "false")
    if totp_secret is None:
        monkeypatch.delenv("DEPLOY_TOTP_SECRET", raising=False)
    else:
        monkeypatch.setenv("DEPLOY_TOTP_SECRET", totp_secret)
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

@pytest.mark.asyncio
async def test_2fa_blocks_sensitive_update_until_authenticated(monkeypatch, tmp_path: Path):
    from titanbox.security import totp_code

    secret = "JBSWY3DPEHPK3PXP"
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(settings=make_settings(monkeypatch, tmp_path / "data2fa", require_2fa=True, totp_secret=secret))
    )
    assert plugin.manager is not None

    import zipfile

    archive = tmp_path / "base.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.py", "VALUE = 1\n")
    await plugin.manager.deploy_zip("securebot", archive)

    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    bot = FakeBot(replacement)
    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": "/use securebot"}},
        bot,
    )
    document_update = {
        "message": {
            "from": {"id": 123},
            "chat": {"id": 1},
            "document": {"file_id": "abc", "file_name": "main.py", "file_size": replacement.stat().st_size},
        }
    }
    await plugin.handle(document_update, bot)
    if plugin._tasks:
        await asyncio.gather(*list(plugin._tasks))
    current = plugin.manager.current_release_path("securebot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 1\n"
    assert any("/auth" in text for text in bot.messages)

    code = totp_code(secret)
    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": f"/auth {code}"}},
        bot,
    )
    await plugin.handle(document_update, bot)
    if plugin._tasks:
        await asyncio.gather(*list(plugin._tasks))
    current = plugin.manager.current_release_path("securebot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 2\n"
    assert plugin.audit is not None and plugin.audit.verify()

@pytest.mark.asyncio
async def test_admin_ignores_group_and_edited_messages(monkeypatch, tmp_path: Path):
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path / "private-only")))
    bot = FakeBot()
    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": -100, "type": "group"}, "text": "/help"}},
        bot,
    )
    await plugin.handle(
        {"edited_message": {"from": {"id": 123}, "chat": {"id": 1, "type": "private"}, "text": "/help"}},
        bot,
    )
    assert bot.messages == []

@pytest.mark.asyncio
async def test_setup_command_never_exposes_secret_values(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "DO_NOT_PRINT_ACCESS")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "DO_NOT_PRINT_SECRET")
    plugin = DeployAdminPlugin()
    plugin.bind_services(PluginServices(settings=make_settings(monkeypatch, tmp_path / "setup-guide")))
    bot = FakeBot()
    await plugin.handle(
        {"message": {"from": {"id": 123}, "chat": {"id": 1}, "text": "/setup"}},
        bot,
    )
    joined = "\n".join(bot.messages)
    assert "STORAGE_BACKEND=s3" in joined
    assert "DO_NOT_PRINT_ACCESS" not in joined
    assert "DO_NOT_PRINT_SECRET" not in joined

class FakePersistentDatabase:
    enabled = True

    def __init__(self):
        self.last_job = None
        self.completed: list[int] = []
        self.failed: list[int] = []

    async def enqueue_job(self, unique_key, kind, payload, *, max_attempts=5):
        self.last_job = {
            "id": 41,
            "unique_key": unique_key,
            "kind": kind,
            "payload": payload,
            "state": "queued",
            "attempts": 0,
            "max_attempts": max_attempts,
        }
        return dict(self.last_job)

    async def complete_job(self, job_id):
        self.completed.append(int(job_id))

    async def fail_job(self, job_id, error, *, retry, retry_delay_seconds=5):
        self.failed.append(int(job_id))
        return "failed"

    async def append_audit(self, record):
        return None


class FakeInfrastructure:
    def __init__(self, database, releases=None):
        self.database = database
        self.releases = releases


@pytest.mark.asyncio
async def test_persistent_document_job_is_enqueued_before_execution_and_can_resume(monkeypatch, tmp_path: Path):
    import zipfile

    archive = tmp_path / "queued.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.py", "VALUE = 11\n")
    bot = FakeBot(archive)
    db = FakePersistentDatabase()
    infra = FakeInfrastructure(db)
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "queued-data"),
            infrastructure=infra,
            bot_context=bot,
        )
    )

    update = {
        "update_id": 9001,
        "message": {
            "from": {"id": 123},
            "chat": {"id": 1, "type": "private"},
            "document": {"file_id": "zip-file", "file_name": "queued.zip", "file_size": archive.stat().st_size},
            "caption": "/deploy queuedbot",
        },
    }
    await plugin.handle(update, bot)
    assert db.last_job is not None
    assert db.last_job["unique_key"] == "deploy-admin:9001:document"
    assert plugin.manager is not None
    assert plugin.manager.current_release_path("queuedbot") is None

    claimed = dict(db.last_job)
    claimed["state"] = "running"
    claimed["attempts"] = 1
    await plugin._process_job(claimed, bot)
    current = plugin.manager.current_release_path("queuedbot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 11\n"
    assert db.completed == [41]
    assert db.failed == []

class FailNotifyBot(FakeBot):
    async def send_message(self, chat_id, text, **extra):
        raise RuntimeError("telegram notification outage")


@pytest.mark.asyncio
async def test_persistent_job_does_not_replay_side_effect_when_notification_fails(monkeypatch, tmp_path: Path):
    import zipfile

    archive = tmp_path / "notify-fail.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.py", "VALUE = 77\n")
    bot = FailNotifyBot(archive)
    db = FakePersistentDatabase()
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "notify-data"),
            infrastructure=FakeInfrastructure(db),
            bot_context=bot,
        )
    )
    job = {
        "id": 51,
        "kind": "document",
        "state": "running",
        "attempts": 1,
        "max_attempts": 5,
        "payload": {
            "actor_id": 123,
            "chat_id": 1,
            "message": {
                "document": {"file_id": "f", "file_name": "notify-fail.zip", "file_size": archive.stat().st_size},
                "caption": "/deploy notifybot",
            },
        },
    }
    await plugin._process_job(job, bot)
    assert plugin.manager is not None
    assert plugin.manager.current_release_path("notifybot") is not None
    assert db.completed == [51]
    assert db.failed == []

@pytest.mark.asyncio
async def test_persistent_smart_update_freezes_active_project_and_path(monkeypatch, tmp_path: Path):
    import zipfile

    archive = tmp_path / "smart-base.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("src/main.py", "VALUE = 1\n")
        zf.writestr("README.txt", "keep src directory\n")
    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    bot = FakeBot(replacement)
    db = FakePersistentDatabase()
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "smart-queued"),
            infrastructure=FakeInfrastructure(db),
            bot_context=bot,
        )
    )
    assert plugin.manager is not None
    await plugin.manager.deploy_zip("medical", archive)
    await plugin.handle(
        {"update_id": 7000, "message": {"from": {"id": 123}, "chat": {"id": 1, "type": "private"}, "text": "/use medical"}},
        bot,
    )
    await plugin.handle(
        {
            "update_id": 7001,
            "message": {
                "from": {"id": 123},
                "chat": {"id": 1, "type": "private"},
                "document": {"file_id": "f1", "file_name": "main.py", "file_size": replacement.stat().st_size},
            },
        },
        bot,
    )
    assert db.last_job is not None
    queued = db.last_job["payload"]["message"]
    assert queued["caption"] == "/put medical src/main.py"

    # Simulate a cold restart erasing `/use` state. The queued job is still self-contained.
    plugin.active_project.clear()
    claimed = dict(db.last_job)
    claimed["attempts"] = 1
    await plugin._process_job(claimed, bot)
    current = plugin.manager.current_release_path("medical")
    assert current is not None
    assert current.joinpath("src/main.py").read_text() == "VALUE = 2\n"


@pytest.mark.asyncio
async def test_persistent_document_retry_reuses_same_release(monkeypatch, tmp_path: Path):
    import zipfile

    archive = tmp_path / "retry.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.py", "VALUE = 33\n")
    bot = FakeBot(archive)
    db = FakePersistentDatabase()
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "retry-data"),
            infrastructure=FakeInfrastructure(db),
            bot_context=bot,
        )
    )
    update = {
        "update_id": 8801,
        "message": {
            "from": {"id": 123},
            "chat": {"id": 1, "type": "private"},
            "document": {"file_id": "f", "file_name": "retry.zip", "file_size": archive.stat().st_size},
            "caption": "/deploy retrybot",
        },
    }
    await plugin.handle(update, bot)
    assert db.last_job is not None
    claimed = dict(db.last_job)
    claimed["attempts"] = 1
    await plugin._process_job(claimed, bot)
    assert plugin.manager is not None
    first_release = plugin.manager.current_release_name("retrybot")
    assert first_release is not None
    # Simulate a worker replay after the side effect committed but before DB completion was durable.
    claimed2 = dict(db.last_job)
    claimed2["attempts"] = 2
    await plugin._process_job(claimed2, bot)
    assert plugin.manager.current_release_name("retrybot") == first_release
    assert plugin.manager.release_names("retrybot") == [first_release]


@pytest.mark.asyncio
async def test_persistent_rollback_without_release_is_frozen_to_one_target(monkeypatch, tmp_path: Path):
    import zipfile

    bot = FakeBot()
    db = FakePersistentDatabase()
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "rb-queue"),
            infrastructure=FakeInfrastructure(db),
            bot_context=bot,
        )
    )
    assert plugin.manager is not None
    for index in range(3):
        archive = tmp_path / f"rb-{index}.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("main.py", f"VALUE = {index}\n")
        await plugin.manager.deploy_zip("rb", archive)
    before = plugin.manager.release_names("rb")
    expected_target = next(name for name in before if name != plugin.manager.current_release_name("rb"))
    await plugin.handle(
        {"update_id": 9901, "message": {"from": {"id": 123}, "chat": {"id": 1, "type": "private"}, "text": "/rollback rb"}},
        bot,
    )
    assert db.last_job is not None
    assert db.last_job["payload"]["release"] == expected_target
    claimed = dict(db.last_job)
    claimed["attempts"] = 1
    await plugin._process_job(claimed, bot)
    claimed2 = dict(db.last_job)
    claimed2["attempts"] = 2
    await plugin._process_job(claimed2, bot)
    assert plugin.manager.current_release_name("rb") == expected_target


class FakeDurableList:
    enabled = True

    async def list_releases(self, project: str, limit: int = 30):
        return ["durable-new", "durable-old"][:limit]


@pytest.mark.asyncio
async def test_persistent_restore_latest_is_frozen_before_enqueue(monkeypatch, tmp_path: Path):
    bot = FakeBot()
    db = FakePersistentDatabase()
    plugin = DeployAdminPlugin()
    plugin.bind_services(
        PluginServices(
            settings=make_settings(monkeypatch, tmp_path / "restore-queue"),
            infrastructure=FakeInfrastructure(db, FakeDurableList()),
            bot_context=bot,
        )
    )
    await plugin.handle(
        {"update_id": 9911, "message": {"from": {"id": 123}, "chat": {"id": 1, "type": "private"}, "text": "/restore medical latest"}},
        bot,
    )
    assert db.last_job is not None
    assert db.last_job["payload"]["release"] == "durable-new"
