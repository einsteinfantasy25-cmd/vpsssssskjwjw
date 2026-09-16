import json

import pytest

from titanbox.settings import Settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("BOTS_JSON", "[]")
    s = Settings.from_env()
    assert s.port == 10000
    assert s.bot_descriptors() == []


def test_bad_bots_json(monkeypatch):
    monkeypatch.setenv("BOTS_JSON", "not-json")
    s = Settings.from_env()
    with pytest.raises(ValueError):
        s.bot_descriptors()


def test_terminal_requires_long_password(monkeypatch):
    monkeypatch.setenv("ENABLE_TERMINAL", "true")
    monkeypatch.setenv("TERMINAL_USER", "admin")
    monkeypatch.setenv("TERMINAL_PASSWORD", "short")
    s = Settings.from_env()
    with pytest.raises(ValueError):
        s.validate()


def test_deploy_admin_plugin_requires_allowlist(monkeypatch):
    monkeypatch.setenv(
        "BOTS_JSON",
        '[{"name":"deploy-admin","token_env":"T","secret_env":"S","plugin":"titanbox.plugins.deploy_admin:DeployAdminPlugin"}]',
    )
    monkeypatch.delenv("DEPLOY_ADMIN_TELEGRAM_IDS", raising=False)
    s = Settings.from_env()
    with pytest.raises(ValueError, match="DEPLOY_ADMIN_TELEGRAM_IDS"):
        s.validate()


def test_deploy_admin_ids_parse(monkeypatch):
    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("DEPLOY_ADMIN_TELEGRAM_IDS", "123, 456")
    s = Settings.from_env()
    assert s.deploy_admin_ids() == {123, 456}
