import asyncio
import stat
import zipfile
from pathlib import Path

import pytest

from titanbox.deploy import DeployError, DeployLimits, DeploymentManager


def manager(tmp_path: Path, **overrides):
    values = {
        "max_upload_bytes": 10_000_000,
        "max_archive_files": 100,
        "max_extracted_bytes": 20_000_000,
        "keep_releases": 4,
        "stabilize_seconds": 0.1,
        "restart_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return DeploymentManager(tmp_path / "data", DeployLimits(**values))


def make_zip(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.mark.parametrize(
    "bad",
    ["../x.py", "/etc/passwd", "a/../../b", "", "./x.py", "a//b.py"],
)
def test_rejects_unsafe_relative_paths(tmp_path: Path, bad: str):
    mgr = manager(tmp_path)
    with pytest.raises(DeployError):
        mgr.validate_relative_path(bad)


@pytest.mark.asyncio
async def test_deploy_update_and_rollback(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"myapp/main.py": "VALUE = 1\n", "myapp/assets/logo.txt": "old"})

    first = await mgr.deploy_zip("mybot", archive)
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert (current / "main.py").read_text() == "VALUE = 1\n"
    assert first.previous_release is None

    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    second = await mgr.put_file("mybot", "main.py", replacement)
    assert second.previous_release == first.release
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert (current / "main.py").read_text() == "VALUE = 2\n"

    rolled = await mgr.rollback("mybot")
    assert rolled.release == first.release
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert (current / "main.py").read_text() == "VALUE = 1\n"


@pytest.mark.asyncio
async def test_bad_python_update_never_becomes_current(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    first = await mgr.deploy_zip("mybot", archive)

    bad = tmp_path / "main.py"
    bad.write_text("def broken(:\n")
    with pytest.raises(DeployError):
        await mgr.put_file("mybot", "main.py", bad)

    assert mgr.current_release_name("mybot") == first.release
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 1\n"


@pytest.mark.asyncio
async def test_zip_slip_is_rejected_and_writes_nothing_outside(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "evil.zip"
    make_zip(archive, {"../escaped.txt": "nope", "main.py": "pass\n"})
    escaped = tmp_path / "escaped.txt"

    with pytest.raises(DeployError):
        await mgr.deploy_zip("evil", archive)
    assert not escaped.exists()
    assert mgr.current_release_name("evil") is None


@pytest.mark.asyncio
async def test_zip_symlink_is_rejected(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")

    with pytest.raises(DeployError):
        await mgr.deploy_zip("evil", archive)


@pytest.mark.asyncio
async def test_archive_limits_are_enforced(tmp_path: Path):
    mgr = manager(tmp_path, max_archive_files=2)
    archive = tmp_path / "many.zip"
    make_zip(archive, {"a": "1", "b": "2", "c": "3"})
    with pytest.raises(DeployError):
        await mgr.deploy_zip("many", archive)


def test_smart_basename_lookup(tmp_path: Path):
    mgr = manager(tmp_path)
    releases = mgr.releases_dir("x")
    release = releases / "20260101-000000-aaaaaaaa"
    (release / "a").mkdir(parents=True)
    (release / "b").mkdir(parents=True)
    (release / "a" / "logo.png").write_bytes(b"a")
    (release / "b" / "logo.png").write_bytes(b"b")
    (mgr.project_dir("x") / "current").symlink_to(Path("releases") / release.name)
    assert mgr.find_by_basename("x", "logo.png") == ["a/logo.png", "b/logo.png"]

class FakeRunner:
    def __init__(self, outcomes: list[bool]):
        self.states = {"mybot": object()}
        self.outcomes = outcomes
        self.restart_calls = 0

    async def restart_app(self, name: str):
        assert name == "mybot"
        self.restart_calls += 1
        return {}

    async def wait_healthy(self, name: str, grace_seconds: float, timeout_seconds: float):
        assert name == "mybot"
        return self.outcomes.pop(0)


@pytest.mark.asyncio
async def test_failed_restart_restores_previous_release(tmp_path: Path):
    runner = FakeRunner([True, False, True])
    limits = DeployLimits(
        max_upload_bytes=10_000_000,
        max_archive_files=100,
        max_extracted_bytes=20_000_000,
        keep_releases=4,
        stabilize_seconds=0.1,
        restart_timeout_seconds=1.0,
    )
    mgr = DeploymentManager(tmp_path / "data", limits, runner=runner)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    first = await mgr.deploy_zip("mybot", archive)

    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    with pytest.raises(DeployError, match="previous state was restored"):
        await mgr.put_file("mybot", "main.py", replacement)

    assert mgr.current_release_name("mybot") == first.release
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert current.joinpath("main.py").read_text() == "VALUE = 1\n"
    assert runner.restart_calls == 3

@pytest.mark.asyncio
async def test_invalid_json_or_toml_is_rejected(tmp_path: Path):
    mgr = manager(tmp_path)
    bad_json = tmp_path / "bad-json.zip"
    make_zip(bad_json, {"config.json": "{broken"})
    with pytest.raises(DeployError, match="Validation failed"):
        await mgr.deploy_zip("jsonbad", bad_json)

    bad_toml = tmp_path / "bad-toml.zip"
    make_zip(bad_toml, {"config.toml": "[broken"})
    with pytest.raises(DeployError, match="Validation failed"):
        await mgr.deploy_zip("tomlbad", bad_toml)


@pytest.mark.asyncio
async def test_concurrent_updates_do_not_corrupt_project(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 0\n"})
    await mgr.deploy_zip("mybot", archive)

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("VALUE = 1\n")
    b.write_text("VALUE = 2\n")
    await asyncio.gather(
        mgr.put_file("mybot", "main.py", a),
        mgr.put_file("mybot", "main.py", b),
    )
    current = mgr.current_release_path("mybot")
    assert current is not None
    assert current.joinpath("main.py").read_text() in {"VALUE = 1\n", "VALUE = 2\n"}
    assert len(mgr.release_names("mybot")) == 3

@pytest.mark.asyncio
async def test_release_integrity_manifest_blocks_tampered_rollback(tmp_path: Path):
    mgr = manager(tmp_path)
    first_zip = tmp_path / "first.zip"
    second_zip = tmp_path / "second.zip"
    make_zip(first_zip, {"main.py": "VALUE = 1\n"})
    make_zip(second_zip, {"main.py": "VALUE = 2\n"})
    first = await mgr.deploy_zip("securebot", first_zip)
    second = await mgr.deploy_zip("securebot", second_zip)
    assert mgr.current_release_name("securebot") == second.release

    old_release = mgr.releases_dir("securebot") / first.release
    old_release.joinpath("main.py").write_text("TAMPERED = True\n")
    with pytest.raises(DeployError, match="integrity"):
        await mgr.rollback("securebot", first.release)
    assert mgr.current_release_name("securebot") == second.release


def test_release_manifest_is_hidden_from_normal_file_listing(tmp_path: Path):
    import asyncio

    mgr = manager(tmp_path)
    archive = tmp_path / "app-manifest.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    asyncio.run(mgr.deploy_zip("manifestbot", archive))
    assert ".titanbox-release.json" not in mgr.list_files("manifestbot")

@pytest.mark.asyncio
async def test_releases_do_not_share_hardlinked_inodes(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "hardlink-base.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n", "config.txt": "stable\n"})
    first = await mgr.deploy_zip("isobot", archive)
    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    second = await mgr.put_file("isobot", "main.py", replacement)

    first_config = mgr.releases_dir("isobot") / first.release / "config.txt"
    second_config = mgr.releases_dir("isobot") / second.release / "config.txt"
    assert first_config.stat().st_ino != second_config.stat().st_ino
    second_config.write_text("changed in current\n")
    assert first_config.read_text() == "stable\n"


def test_rejects_invisible_unicode_in_paths_and_filenames(tmp_path: Path):
    mgr = manager(tmp_path)
    with pytest.raises(DeployError, match="invisible"):
        mgr.validate_relative_path("safe/evil\u202etxt.py")
    with pytest.raises(DeployError, match="invisible"):
        mgr.safe_filename("evil\u202etxt.py")


@pytest.mark.asyncio
async def test_zip_duplicate_normalized_path_is_rejected(tmp_path: Path):
    mgr = manager(tmp_path)
    archive = tmp_path / "duplicate.zip"
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("main.py", "VALUE = 1\n")
            # A ZIP may legally contain duplicate entries. Deployment must not depend on which
            # duplicate extractor ordering happens to win.
            zf.writestr("main.py", "VALUE = 2\n")
    with pytest.raises(DeployError, match="duplicate normalized path"):
        await mgr.deploy_zip("duplicate", archive)


class FakeDurableStore:
    enabled = True

    def __init__(self, fail: bool = False, promote_fail: bool = False):
        self.fail = fail
        self.promote_fail = promote_fail
        self.backups: list[tuple[str, str]] = []
        self.active: list[tuple[str, str]] = []
        self.abandoned: list[tuple[str, str]] = []

    async def backup_release(self, project: str, release: str, release_root: Path):
        if self.fail:
            raise RuntimeError("storage down")
        self.backups.append((project, release))
        return {"project": project, "release": release, "state": "candidate"}

    async def promote_release(self, project: str, release: str):
        if self.promote_fail:
            raise RuntimeError("storage commit down")
        self.active.append((project, release))
        return {"project": project, "release": release, "state": "active"}

    async def abandon_release(self, project: str, release: str):
        self.abandoned.append((project, release))
        self.active = [item for item in self.active if item != (project, release)]

    async def list_releases(self, project: str, limit: int = 30):
        return [release for name, release in self.active if name == project][:limit]

    async def latest_release(self, project: str):
        items = [release for name, release in self.active if name == project]
        return items[-1] if items else None


@pytest.mark.asyncio
async def test_required_durable_backup_happens_before_activation(tmp_path: Path):
    limits = DeployLimits(
        max_upload_bytes=10_000_000, max_archive_files=100, max_extracted_bytes=20_000_000,
        keep_releases=4, stabilize_seconds=0.1, restart_timeout_seconds=1.0,
    )
    durable = FakeDurableStore(fail=True)
    mgr = DeploymentManager(tmp_path / "data", limits, durable_store=durable, durability_required=True)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    with pytest.raises(DeployError, match="Durable backup failed"):
        await mgr.deploy_zip("mybot", archive)
    assert mgr.current_release_name("mybot") is None


@pytest.mark.asyncio
async def test_optional_durable_failure_marks_warning_and_activates(tmp_path: Path):
    limits = DeployLimits(
        max_upload_bytes=10_000_000, max_archive_files=100, max_extracted_bytes=20_000_000,
        keep_releases=4, stabilize_seconds=0.1, restart_timeout_seconds=1.0,
    )
    durable = FakeDurableStore(fail=True)
    mgr = DeploymentManager(tmp_path / "data", limits, durable_store=durable, durability_required=False)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    result = await mgr.deploy_zip("mybot", archive)
    assert "persistent-backup:warning" in result.validation
    assert mgr.current_release_name("mybot") == result.release


@pytest.mark.asyncio
async def test_successful_durable_backup_is_promoted_only_after_activation(tmp_path: Path):
    limits = DeployLimits(
        max_upload_bytes=10_000_000, max_archive_files=100, max_extracted_bytes=20_000_000,
        keep_releases=4, stabilize_seconds=0.1, restart_timeout_seconds=1.0,
    )
    durable = FakeDurableStore()
    mgr = DeploymentManager(tmp_path / "data", limits, durable_store=durable, durability_required=True)
    archive = tmp_path / "app.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    result = await mgr.deploy_zip("mybot", archive)
    assert "persistent-backup:candidate-ok" in result.validation
    assert "persistent-backup:active-ok" in result.validation
    assert durable.backups == [("mybot", result.release)]
    assert durable.active == [("mybot", result.release)]


@pytest.mark.asyncio
async def test_required_durable_promotion_failure_restores_previous_release(tmp_path: Path):
    runner = FakeRunner([True, True, True])
    limits = DeployLimits(
        max_upload_bytes=10_000_000, max_archive_files=100, max_extracted_bytes=20_000_000,
        keep_releases=4, stabilize_seconds=0.1, restart_timeout_seconds=1.0,
    )
    durable = FakeDurableStore()
    mgr = DeploymentManager(tmp_path / "data", limits, runner=runner, durable_store=durable, durability_required=True)
    archive = tmp_path / "first.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    first = await mgr.deploy_zip("mybot", archive)
    durable.promote_fail = True
    replacement = tmp_path / "main.py"
    replacement.write_text("VALUE = 2\n")
    with pytest.raises(DeployError, match="Durable commit failed"):
        await mgr.put_file("mybot", "main.py", replacement)
    assert mgr.current_release_name("mybot") == first.release
    assert durable.abandoned


class FirstDeployFailRunner:
    def __init__(self):
        self.states = {"mybot": object()}
        self.stopped = 0

    async def restart_app(self, name: str):
        return {}

    async def wait_healthy(self, name: str, grace_seconds: float, timeout_seconds: float):
        return False

    async def stop_app(self, name: str):
        self.stopped += 1
        return {}


@pytest.mark.asyncio
async def test_first_deploy_runtime_failure_leaves_no_current_pointer(tmp_path: Path):
    runner = FirstDeployFailRunner()
    limits = DeployLimits(
        max_upload_bytes=10_000_000, max_archive_files=100, max_extracted_bytes=20_000_000,
        keep_releases=4, stabilize_seconds=0.1, restart_timeout_seconds=1.0,
    )
    mgr = DeploymentManager(tmp_path / "data", limits, runner=runner)
    archive = tmp_path / "bad-runtime.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    with pytest.raises(DeployError, match="previous state was restored"):
        await mgr.deploy_zip("mybot", archive)
    assert mgr.current_release_name("mybot") is None
    assert runner.stopped == 1

@pytest.mark.asyncio
async def test_deploy_operation_id_is_idempotent_across_job_retry(tmp_path: Path):
    mgr = manager(tmp_path / "idem-data")
    archive = tmp_path / "idem.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    first = await mgr.deploy_zip("idem", archive, operation_id="deploy-admin:123:document")
    second = await mgr.deploy_zip("idem", archive, operation_id="deploy-admin:123:document")
    assert first.release == second.release
    assert mgr.current_release_name("idem") == first.release
    assert mgr.release_names("idem") == [first.release]
    assert "idempotent-replay" in second.validation


@pytest.mark.asyncio
async def test_put_operation_id_is_idempotent_across_job_retry(tmp_path: Path):
    mgr = manager(tmp_path / "idem-put-data")
    archive = tmp_path / "idem-base.zip"
    make_zip(archive, {"main.py": "VALUE = 1\n"})
    base = await mgr.deploy_zip("idemput", archive)
    replacement = tmp_path / "replacement.py"
    replacement.write_text("VALUE = 2\n")
    first = await mgr.put_file("idemput", "main.py", replacement, operation_id="deploy-admin:456:document")
    second = await mgr.put_file("idemput", "main.py", replacement, operation_id="deploy-admin:456:document")
    assert first.release == second.release
    assert mgr.current_release_name("idemput") == first.release
    assert len(mgr.release_names("idemput")) == 2
    assert base.release in mgr.release_names("idemput")
    assert "idempotent-replay" in second.validation


@pytest.mark.asyncio
async def test_idempotent_explicit_rollback_retry_never_walks_back_twice(tmp_path: Path):
    mgr = manager(tmp_path / "rollback-idem")
    a = tmp_path / "a.zip"
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    make_zip(a, {"main.py": "VALUE = 1\n"})
    make_zip(b, {"main.py": "VALUE = 2\n"})
    make_zip(c, {"main.py": "VALUE = 3\n"})
    first = await mgr.deploy_zip("rb", a)
    await mgr.deploy_zip("rb", b)
    await mgr.deploy_zip("rb", c)
    target = mgr.release_names("rb")[1]
    once = await mgr.rollback("rb", target, idempotent=True)
    twice = await mgr.rollback("rb", target, idempotent=True)
    assert once.release == target
    assert twice.release == target
    assert mgr.current_release_name("rb") == target
    assert "rollback:idempotent" in twice.validation
    assert first.release in mgr.release_names("rb")

@pytest.mark.asyncio
async def test_verified_durable_restore_is_not_blocked_by_telegram_upload_limit(tmp_path: Path):
    limits = DeployLimits(
        max_upload_bytes=120,
        max_archive_files=100,
        max_extracted_bytes=20_000,
        keep_releases=4,
        stabilize_seconds=0.1,
        restart_timeout_seconds=1.0,
    )
    mgr = DeploymentManager(tmp_path / "durable-size", limits)
    archive = tmp_path / "larger-than-telegram.zip"
    # Incompressible-ish bytes make the ZIP larger than the tiny simulated Telegram limit,
    # while still staying well inside the extracted-content safety budget.
    import os
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("blob.bin", os.urandom(1000))
    assert archive.stat().st_size > limits.max_upload_bytes
    with pytest.raises(DeployError, match="Upload exceeds"):
        await mgr.deploy_zip("p", archive)
    result = await mgr.deploy_zip("p", archive, trusted_durable_restore=True)
    assert mgr.current_release_name("p") == result.release
