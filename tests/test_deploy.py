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
    with pytest.raises(DeployError, match="previous release was restored"):
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
