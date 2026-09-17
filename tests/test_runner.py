import asyncio
from pathlib import Path

import pytest

from titanbox.runner import AppRunner, load_specs


def test_load_specs(tmp_path: Path):
    cfg = tmp_path / "apps.toml"
    cfg.write_text(
        '[[apps]]\n'
        'name="x"\n'
        'command=["/bin/sh","-c","exit 0"]\n'
        'enabled=false\n'
    )
    specs = load_specs(cfg)
    assert len(specs) == 1
    assert specs[0].name == "x"


@pytest.mark.asyncio
async def test_runner_starts_and_stops_clean_app(tmp_path: Path):
    cfg = tmp_path / "apps.toml"
    cfg.write_text(
        '[[apps]]\n'
        'name="short"\n'
        'command=["/bin/sh","-c","exit 0"]\n'
        f'cwd="{tmp_path}"\n'
        'enabled=true\n'
        'restart="never"\n'
    )
    runner = AppRunner(cfg)
    await runner.start()
    await asyncio.sleep(0.4)
    status = runner.status()[0]
    assert status["last_exit_code"] == 0
    await runner.close()


@pytest.mark.asyncio
async def test_crash_loop_opens_circuit(tmp_path: Path):
    cfg = tmp_path / "apps.toml"
    cfg.write_text(
        '[[apps]]\n'
        'name="crasher"\n'
        'command=["/bin/sh","-c","exit 3"]\n'
        f'cwd="{tmp_path}"\n'
        'enabled=true\n'
        'restart="on-failure"\n'
        'max_restarts=2\n'
        'restart_window_seconds=60\n'
        'backoff_base_seconds=0.1\n'
        'backoff_max_seconds=0.1\n'
    )
    runner = AppRunner(cfg)
    await runner.start()
    await asyncio.sleep(1.0)
    status = runner.status()[0]
    assert status["circuit_open"] is True
    assert status["restart_count"] == 2
    assert status["last_exit_code"] == 3
    await runner.close()


def test_runner_rejects_committed_secret_values(tmp_path: Path):
    cfg = tmp_path / "apps.toml"
    cfg.write_text(
        '[[apps]]\n'
        'name="unsafe"\n'
        'command=["/bin/sh","-c","exit 0"]\n'
        '[apps.env]\n'
        'BOT_TOKEN="do-not-commit-this"\n'
    )
    with pytest.raises(ValueError, match="env_passthrough"):
        load_specs(cfg)
