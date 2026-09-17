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


def test_deploy_admin_allows_safe_discovery_mode_without_allowlist(monkeypatch):
    monkeypatch.setenv(
        "BOTS_JSON",
        '[{"name":"deploy-admin","token_env":"T","plugin":"titanbox.plugins.deploy_admin:DeployAdminPlugin"}]',
    )
    monkeypatch.delenv("DEPLOY_ADMIN_TELEGRAM_IDS", raising=False)
    s = Settings.from_env()
    s.validate()
    assert s.deploy_admin_ids() == set()
    assert any("no authorized Telegram user" in warning for warning in s.setup_warnings())


def test_deploy_admin_ids_parse(monkeypatch):
    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("DEPLOY_ADMIN_TELEGRAM_IDS", "123, 456")
    s = Settings.from_env()
    assert s.deploy_admin_ids() == {123, 456}


def test_zero_admin_id_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("DEPLOY_ADMIN_TELEGRAM_IDS", "0")
    s = Settings.from_env()
    assert s.deploy_admin_ids() == set()


def test_render_public_url_is_auto_detected(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://titanbox-example.onrender.com")
    monkeypatch.setenv("BOTS_JSON", "[]")
    s = Settings.from_env()
    assert s.public_base_url == "https://titanbox-example.onrender.com"
    assert s.platform == "render"


def test_render_first_boot_does_not_require_public_base_url_or_admin_id(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("DEPLOY_ADMIN_TELEGRAM_IDS", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://titanbox-first.onrender.com")
    monkeypatch.setenv("AUTO_REGISTER_WEBHOOKS", "true")
    monkeypatch.setenv(
        "BOTS_JSON",
        '[{"name":"deploy-admin","token_env":"DEPLOY_BOT_TOKEN","plugin":"titanbox.plugins.deploy_admin:DeployAdminPlugin"}]',
    )
    monkeypatch.setenv("DEPLOY_BOT_TOKEN", "123:abc")
    s = Settings.from_env()
    s.validate()
    assert s.public_base_url == "https://titanbox-first.onrender.com"
    assert s.deploy_admin_ids() == set()
