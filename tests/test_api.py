import importlib

from fastapi.testclient import TestClient


def load_app(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import titanbox.main as main
    return importlib.reload(main)


def test_health_and_public_surface(monkeypatch):
    main = load_app(
        monkeypatch,
        BOTS_JSON="[]",
        ENABLE_RUNNER="false",
        ENABLE_TERMINAL="false",
        ADMIN_API_ENABLED="false",
        METRICS_PUBLIC="false",
    )
    with TestClient(main.app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").json()["ok"] is True
        assert "TitanBox" in client.get("/").text
        assert client.get("/setup").status_code == 200
        assert client.get("/status").json()["version"] == "1.0.0"
        assert client.get("/metrics").status_code == 404
        response = client.get("/healthz")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]


def test_metrics_can_be_public_when_explicit(monkeypatch):
    main = load_app(monkeypatch, BOTS_JSON="[]", METRICS_PUBLIC="true")
    with TestClient(main.app) as client:
        text = client.get("/metrics").text
        assert "titanbox_up 1" in text


def test_admin_hidden_without_enable_switch(monkeypatch):
    main = load_app(
        monkeypatch,
        BOTS_JSON="[]",
        ENABLE_RUNNER="false",
        ADMIN_API_ENABLED="false",
        ADMIN_TOKEN="this-is-a-long-admin-secret",
    )
    with TestClient(main.app) as client:
        assert client.get("/admin/status").status_code == 404


def test_admin_auth(monkeypatch):
    main = load_app(
        monkeypatch,
        BOTS_JSON="[]",
        ENABLE_RUNNER="false",
        ADMIN_API_ENABLED="true",
        ADMIN_TOKEN="this-is-a-long-admin-secret",
    )
    with TestClient(main.app) as client:
        assert client.get("/admin/status").status_code == 401
        resp = client.get("/admin/status", headers={"Authorization": "Bearer this-is-a-long-admin-secret"})
        assert resp.status_code == 200
