from __future__ import annotations

import asyncio
import logging
import os
import random
import resource
import signal
import time
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("titanbox.runner")
RestartPolicy = Literal["never", "on-failure", "always"]


@dataclass(slots=True)
class AppSpec:
    name: str
    command: list[str]
    enabled: bool = True
    cwd: str = "/app"
    restart: RestartPolicy = "on-failure"
    max_restarts: int = 5
    restart_window_seconds: int = 300
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    max_open_files: int = 512
    nice: int = 5
    env_passthrough: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "AppSpec":
        allowed = {"never", "on-failure", "always"}
        restart = str(raw.get("restart", "on-failure"))
        if restart not in allowed:
            raise ValueError(f"invalid restart policy for {raw.get('name')}: {restart}")
        cmd = raw.get("command")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) and x for x in cmd):
            raise ValueError("command must be a non-empty array of strings")
        name = str(raw.get("name", "")).strip()
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid app name: {name!r}")
        return cls(
            name=name,
            command=cmd,
            enabled=bool(raw.get("enabled", True)),
            cwd=str(raw.get("cwd", "/app")),
            restart=restart,  # type: ignore[arg-type]
            max_restarts=max(0, int(raw.get("max_restarts", 5))),
            restart_window_seconds=max(1, int(raw.get("restart_window_seconds", 300))),
            backoff_base_seconds=max(0.1, float(raw.get("backoff_base_seconds", 1.0))),
            backoff_max_seconds=max(0.1, float(raw.get("backoff_max_seconds", 30.0))),
            max_open_files=max(64, int(raw.get("max_open_files", 512))),
            nice=max(0, min(19, int(raw.get("nice", 5)))),
            env_passthrough=[str(x) for x in raw.get("env_passthrough", [])],
            env={str(k): str(v) for k, v in raw.get("env", {}).items()},
        )


@dataclass(slots=True)
class AppState:
    spec: AppSpec
    process: asyncio.subprocess.Process | None = None
    monitor_task: asyncio.Task[None] | None = None
    desired_running: bool = True
    restart_times: deque[float] = field(default_factory=deque)
    restart_count: int = 0
    last_exit_code: int | None = None
    last_started_at: float | None = None
    circuit_open: bool = False
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        proc = self.process
        return {
            "name": self.spec.name,
            "enabled": self.spec.enabled,
            "desired_running": self.desired_running,
            "running": bool(proc and proc.returncode is None),
            "pid": proc.pid if proc and proc.returncode is None else None,
            "restart_count": self.restart_count,
            "last_exit_code": self.last_exit_code,
            "last_started_at": self.last_started_at,
            "circuit_open": self.circuit_open,
            "last_error": self.last_error,
            "restart_policy": self.spec.restart,
        }


def load_specs(path: Path) -> list[AppSpec]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    raw_apps = data.get("apps", [])
    if not isinstance(raw_apps, list):
        raise ValueError("apps.toml: [[apps]] entries expected")
    specs = [AppSpec.from_mapping(item) for item in raw_apps]
    names = [x.name for x in specs]
    if len(names) != len(set(names)):
        raise ValueError("duplicate app names in apps.toml")
    return specs


def _apply_post_spawn_limits(pid: int, spec: AppSpec) -> None:
    """Best-effort Linux limits without unsafe preexec_fn usage in a threaded server."""
    try:
        _soft, hard = resource.prlimit(pid, resource.RLIMIT_NOFILE)
        limit = min(spec.max_open_files, hard if hard != resource.RLIM_INFINITY else spec.max_open_files)
        resource.prlimit(pid, resource.RLIMIT_NOFILE, (limit, limit))
    except (AttributeError, OSError, PermissionError):
        pass
    try:
        os.setpriority(os.PRIO_PROCESS, pid, spec.nice)
    except (AttributeError, OSError, PermissionError):
        pass


class AppRunner:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.states: dict[str, AppState] = {}
        self.started = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self.started:
                return
            for spec in load_specs(self.config_path):
                state = AppState(spec=spec, desired_running=spec.enabled)
                self.states[spec.name] = state
                if spec.enabled:
                    state.monitor_task = asyncio.create_task(self._monitor(state), name=f"monitor:{spec.name}")
            self.started = True

    async def close(self) -> None:
        for state in self.states.values():
            state.desired_running = False
        await asyncio.gather(*(self._terminate(s) for s in self.states.values()), return_exceptions=True)
        tasks = [s.monitor_task for s in self.states.values() if s.monitor_task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.started = False

    async def _spawn(self, state: AppState) -> asyncio.subprocess.Process:
        spec = state.spec
        env = {"PATH": os.getenv("PATH", ""), "HOME": os.getenv("HOME", "/home/app"), "PYTHONUNBUFFERED": "1"}
        for key in spec.env_passthrough:
            if key in os.environ:
                env[key] = os.environ[key]
        env.update(spec.env)
        proc = await asyncio.create_subprocess_exec(
            *spec.command,
            cwd=spec.cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        _apply_post_spawn_limits(proc.pid, spec)
        state.process = proc
        state.last_error = None
        state.last_started_at = time.time()
        log.info("started app=%s pid=%s", spec.name, proc.pid)
        asyncio.create_task(self._pipe_logs(spec.name, "stdout", proc.stdout))
        asyncio.create_task(self._pipe_logs(spec.name, "stderr", proc.stderr))
        return proc

    async def _pipe_logs(self, name: str, stream_name: str, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if stream_name == "stderr":
                log.warning("[%s] %s", name, text)
            else:
                log.info("[%s] %s", name, text)

    def _should_restart(self, state: AppState, exit_code: int) -> bool:
        if not state.desired_running:
            return False
        policy = state.spec.restart
        return policy == "always" or (policy == "on-failure" and exit_code != 0)

    def _record_restart(self, state: AppState) -> bool:
        now = time.monotonic()
        window = state.spec.restart_window_seconds
        while state.restart_times and now - state.restart_times[0] > window:
            state.restart_times.popleft()
        if len(state.restart_times) >= state.spec.max_restarts:
            state.circuit_open = True
            return False
        state.restart_times.append(now)
        state.restart_count += 1
        return True

    async def _monitor(self, state: AppState) -> None:
        while state.desired_running:
            if state.circuit_open:
                return
            try:
                proc = await self._spawn(state)
                exit_code = await proc.wait()
                state.last_exit_code = exit_code
                state.process = None
                log.warning("app exited name=%s code=%s", state.spec.name, exit_code)
                if not self._should_restart(state, exit_code):
                    return
                if not self._record_restart(state):
                    log.error("circuit opened for app=%s after crash loop", state.spec.name)
                    return
                exponent = max(0, state.restart_count - 1)
                delay = min(state.spec.backoff_max_seconds, state.spec.backoff_base_seconds * (2**exponent))
                delay *= random.uniform(0.85, 1.15)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("monitor failure app=%s", state.spec.name)
                if not self._record_restart(state):
                    return
                await asyncio.sleep(min(state.spec.backoff_max_seconds, state.spec.backoff_base_seconds))

    async def _terminate(self, state: AppState, timeout: float = 8.0) -> None:
        proc = state.process
        if not proc or proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        finally:
            state.process = None

    async def stop_app(self, name: str) -> dict[str, Any]:
        state = self.states[name]
        state.desired_running = False
        await self._terminate(state)
        if state.monitor_task and not state.monitor_task.done():
            state.monitor_task.cancel()
            await asyncio.gather(state.monitor_task, return_exceptions=True)
        state.monitor_task = None
        return state.as_dict()

    async def start_app(self, name: str) -> dict[str, Any]:
        state = self.states[name]
        if state.process and state.process.returncode is None:
            return state.as_dict()
        if state.monitor_task and not state.monitor_task.done() and state.desired_running:
            return state.as_dict()
        state.desired_running = True
        state.circuit_open = False
        state.last_error = None
        state.restart_times.clear()
        state.monitor_task = asyncio.create_task(self._monitor(state), name=f"monitor:{name}")
        return state.as_dict()

    async def restart_app(self, name: str) -> dict[str, Any]:
        state = self.states[name]
        state.desired_running = False
        await self._terminate(state)
        if state.monitor_task:
            state.monitor_task.cancel()
            await asyncio.gather(state.monitor_task, return_exceptions=True)
        state.desired_running = True
        state.circuit_open = False
        state.restart_times.clear()
        state.monitor_task = asyncio.create_task(self._monitor(state), name=f"monitor:{name}")
        return state.as_dict()

    async def wait_healthy(self, name: str, grace_seconds: float = 2.0, timeout_seconds: float = 12.0) -> bool:
        state = self.states[name]
        deadline = time.monotonic() + timeout_seconds
        stable_since: float | None = None
        while time.monotonic() < deadline:
            process = state.process
            running = bool(process and process.returncode is None and not state.circuit_open)
            if running:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= grace_seconds:
                    return True
            else:
                stable_since = None
                if state.circuit_open:
                    return False
            await asyncio.sleep(0.1)
        return False

    def status(self) -> list[dict[str, Any]]:
        return [self.states[name].as_dict() for name in sorted(self.states)]
