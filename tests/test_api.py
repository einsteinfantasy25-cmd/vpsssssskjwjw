import importlib

from fastapi.testclient import TestClient


def load_app(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import titanbox.main as main
    return importlib.reload(main)


def test_health_and_metrics(monkeypatch):
    main = load_app(monkeypatch, BOTS_JSON="[]", ENABLE_RUNNER="false", ENABLE_TERMINAL="false")
    with TestClient(main.app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").json()["ok"] is True
        assert "TitanBox" in client.get("/").text
        assert client.get("/setup").status_code == 200
        assert client.get("/status").json()["version"] == "0.3.0"
        text = client.get("/metrics").text
        assert "titanbox_up 1" in text


def test_admin_hidden_without_token(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    main = load_app(monkeypatch, BOTS_JSON="[]", ENABLE_RUNNER="false")
    with TestClient(main.app) as client:
        assert client.get("/admin/status").status_code == 404


def test_admin_auth(monkeypatch):
    main = load_app(monkeypatch, BOTS_JSON="[]", ENABLE_RUNNER="false", ADMIN_TOKEN="this-is-a-long-admin-secret")
    with TestClient(main.app) as client:
        assert client.get("/admin/status").status_code == 401
        resp = client.get("/admin/status", headers={"Authorization": "Bearer this-is-a-long-admin-secret"})
        assert resp.status_code == 200
