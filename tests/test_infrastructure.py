from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from titanbox.settings import Settings
from titanbox.storage import DurableReleaseStore, StorageError


class MemoryObjectStore:
    enabled = True

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def put_file(self, key: str, path: Path, *, content_type: str | None = None) -> None:
        self.objects[key] = path.read_bytes()

    async def get_file(self, key: str, destination: Path) -> None:
        destination.write_bytes(self.objects[key])

    async def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = data

    async def get_bytes(self, key: str, *, max_bytes: int = 2_000_000) -> bytes:
        data = self.objects[key]
        if len(data) > max_bytes:
            raise StorageError("too large")
        return data

    async def list_keys(self, prefix: str, *, limit: int = 1000) -> list[str]:
        return sorted([key for key in self.objects if key.startswith(prefix)], reverse=True)[:limit]

    async def delete_key(self, key: str) -> None:
        self.objects.pop(key, None)

    async def health(self):
        return {"enabled": True, "ok": True, "backend": "memory", "latency_ms": 0.1}


@pytest.mark.asyncio
async def test_durable_release_is_not_latest_until_promoted(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem)  # type: ignore[arg-type]
    release = tmp_path / "release"
    release.mkdir()
    (release / "main.py").write_text("print('ok')\n")
    meta = await store.backup_release("medical", "20260917-a1", release)
    assert meta["state"] == "candidate"
    assert await store.latest_release("medical") is None
    with pytest.raises(StorageError, match="active"):
        await store.download_archive("medical", "20260917-a1", tmp_path / "no.zip")

    promoted = await store.promote_release("medical", "20260917-a1")
    assert promoted["state"] == "active"
    assert await store.latest_release("medical") == "20260917-a1"
    assert await store.list_releases("medical") == ["20260917-a1"]

    destination = tmp_path / "download.zip"
    restored = await store.download_archive("medical", "20260917-a1", destination)
    assert restored["sha256"] == meta["sha256"]
    assert destination.exists()


@pytest.mark.asyncio
async def test_durable_release_rejects_corrupted_archive(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem)  # type: ignore[arg-type]
    release = tmp_path / "release"
    release.mkdir()
    (release / "a.txt").write_text("A")
    await store.backup_release("p", "r1", release)
    await store.promote_release("p", "r1")
    mem.objects["releases/p/r1.zip"] += b"corruption"
    with pytest.raises(StorageError, match="verification failed"):
        await store.download_archive("p", "r1", tmp_path / "bad.zip")


@pytest.mark.asyncio
async def test_abandoned_candidate_never_appears_in_restore_list(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem)  # type: ignore[arg-type]
    release = tmp_path / "release"
    release.mkdir()
    (release / "a.txt").write_text("A")
    await store.backup_release("p", "candidate1", release)
    await store.abandon_release("p", "candidate1")
    assert await store.list_releases("p") == []
    assert not any("candidate1" in key for key in mem.objects)


def test_s3_settings_require_credentials(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
    settings = Settings.from_env()
    with pytest.raises(ValueError, match="S3_BUCKET"):
        settings.validate()


def test_required_database_needs_dsn(monkeypatch):
    monkeypatch.setenv("DATABASE_REQUIRED", "true")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    settings = Settings.from_env()
    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        settings.validate()


def test_postgres_password_is_redacted_secret(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:very-secret-password@example/db")
    settings = Settings.from_env()
    assert "very-secret-password" in settings.known_secret_values()


def test_wake_endpoint(monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("BOTS_JSON", "[]")
    monkeypatch.setenv("ENABLE_RUNNER", "false")
    monkeypatch.setenv("WAKE_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("STORAGE_BACKEND", "none")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("DATABASE_REQUIRED", "false")
    sys.modules.pop("titanbox.main", None)
    main = importlib.import_module("titanbox.main")
    with TestClient(main.app) as client:
        response = client.get("/wakez")
        assert response.status_code == 200
        assert response.json()["awake"] is True
        assert response.json()["version"] == "1.0.0"


def test_render_blueprint_keeps_persistence_operator_managed():
    text = Path("render.yaml").read_text()
    assert "key: WAKE_ENDPOINT_ENABLED" in text
    assert "key: WEBHOOK_REGISTER_BACKGROUND" in text
    assert "key: RELEASE_SIGNING_KEY" in text
    # Optional provider settings are deliberately absent from the Blueprint. This avoids
    # first-deploy prompts and prevents a later Blueprint sync from resetting manual values.
    assert "key: STORAGE_BACKEND" not in text
    assert "key: S3_ACCESS_KEY_ID" not in text
    assert "key: POSTGRES_DSN" not in text
    assert "key: DEPLOY_REQUIRE_2FA" not in text

@pytest.mark.asyncio
async def test_durable_release_hmac_detects_metadata_tampering(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem, signing_key="K" * 48)  # type: ignore[arg-type]
    release = tmp_path / "release-hmac"
    release.mkdir()
    (release / "main.py").write_text("print('signed')\n")
    await store.backup_release("medical", "signed1", release)

    metadata = json.loads(mem.objects["releases/medical/signed1.json"])
    metadata["sha256"] = "0" * 64
    mem.objects["releases/medical/signed1.json"] = json.dumps(metadata).encode()
    with pytest.raises(StorageError, match="signature verification failed"):
        await store.promote_release("medical", "signed1")


@pytest.mark.asyncio
async def test_durable_release_hmac_detects_active_marker_tampering(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem, signing_key="S" * 48)  # type: ignore[arg-type]
    release = tmp_path / "release-marker"
    release.mkdir()
    (release / "main.py").write_text("print('ok')\n")
    await store.backup_release("medical", "signed2", release)
    await store.promote_release("medical", "signed2")

    marker = json.loads(mem.objects["releases/medical/signed2.active.json"])
    marker["sha256"] = "f" * 64
    mem.objects["releases/medical/signed2.active.json"] = json.dumps(marker).encode()
    with pytest.raises(StorageError, match="signature verification failed"):
        await store.download_archive("medical", "signed2", tmp_path / "tampered.zip")


def test_s3_automatically_defaults_to_required_durability(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("DURABILITY_REQUIRED", raising=False)
    settings = Settings.from_env()
    assert settings.durability_required is True


def test_postgres_automatically_defaults_to_required_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@example.com/db")
    monkeypatch.delenv("DATABASE_REQUIRED", raising=False)
    settings = Settings.from_env()
    assert settings.database_required is True


def test_release_signing_key_is_redacted_secret(monkeypatch):
    key = "release-signing-key-" + "x" * 40
    monkeypatch.setenv("RELEASE_SIGNING_KEY", key)
    settings = Settings.from_env()
    assert key in settings.known_secret_values()


def test_s3_requires_release_signing_key(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("RELEASE_SIGNING_KEY", raising=False)
    settings = Settings.from_env()
    with pytest.raises(ValueError, match="RELEASE_SIGNING_KEY"):
        settings.validate()

@pytest.mark.asyncio
async def test_durable_release_listing_uses_signed_activation_time_not_release_name(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem)  # type: ignore[arg-type]
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "a.txt").write_text("one")
    (two / "a.txt").write_text("two")
    # Deliberately choose names whose lexical order is the opposite of activation order.
    await store.backup_release("p", "zzzz-old", one)
    await store.promote_release("p", "zzzz-old")
    await store.backup_release("p", "aaaa-new", two)
    await store.promote_release("p", "aaaa-new")

    old_marker = json.loads(mem.objects["releases/p/zzzz-old.active.json"])
    new_marker = json.loads(mem.objects["releases/p/aaaa-new.active.json"])
    old_marker["activated_at"] = 10
    new_marker["activated_at"] = 20
    mem.objects["releases/p/zzzz-old.active.json"] = json.dumps(old_marker).encode()
    mem.objects["releases/p/aaaa-new.active.json"] = json.dumps(new_marker).encode()

    assert await store.list_releases("p") == ["aaaa-new", "zzzz-old"]


@pytest.mark.asyncio
async def test_signed_latest_pointer_tampering_fails_closed(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem, signing_key="P" * 48)  # type: ignore[arg-type]
    release = tmp_path / "signed-latest"
    release.mkdir()
    (release / "main.py").write_text("print('ok')\n")
    await store.backup_release("p", "r1", release)
    await store.promote_release("p", "r1")
    pointer = json.loads(mem.objects["releases/p/latest.json"])
    pointer["release"] = "attacker-choice"
    mem.objects["releases/p/latest.json"] = json.dumps(pointer).encode()
    with pytest.raises(StorageError, match="signature verification failed"):
        await store.latest_release("p")

@pytest.mark.asyncio
async def test_latest_pointer_recovers_after_ambiguous_abandoned_commit(tmp_path):
    mem = MemoryObjectStore()
    store = DurableReleaseStore(mem, signing_key="R" * 48)  # type: ignore[arg-type]
    old = tmp_path / "old-release"
    old.mkdir()
    (old / "a").write_text("old")
    new = tmp_path / "new-release"
    new.mkdir()
    (new / "a").write_text("new")
    await store.backup_release("p", "old", old)
    await store.promote_release("p", "old")
    await store.backup_release("p", "new", new)
    await store.promote_release("p", "new")
    # Simulate the network-ambiguity window: latest pointer reached object storage, then the
    # caller abandoned the candidate after seeing an error.
    await store.abandon_release("p", "new")
    assert await store.latest_release("p") == "old"
    repaired = json.loads(mem.objects["releases/p/latest.json"])
    assert repaired["release"] == "old"


def test_custom_s3_endpoint_defaults_to_path_style(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://account.example-s3.invalid")
    monkeypatch.delenv("S3_FORCE_PATH_STYLE", raising=False)
    settings = Settings.from_env()
    assert settings.s3_force_path_style is True
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "false")
    settings = Settings.from_env()
    assert settings.s3_force_path_style is False
