from __future__ import annotations

import os
import resource
import time
from pathlib import Path

STARTED_AT = time.monotonic()


def _read_int(path: str) -> int | None:
    try:
        raw = Path(path).read_text().strip()
        if raw == "max":
            return None
        return int(raw)
    except (OSError, ValueError):
        return None


def cgroup_memory() -> dict[str, int | None]:
    # cgroup v2 first; common on modern PaaS containers.
    current = _read_int("/sys/fs/cgroup/memory.current")
    limit = _read_int("/sys/fs/cgroup/memory.max")
    if current is not None or limit is not None:
        return {"current_bytes": current, "limit_bytes": limit}

    # cgroup v1 fallback.
    current = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    limit = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    return {"current_bytes": current, "limit_bytes": limit}


def process_rss_bytes() -> int:
    # ru_maxrss is KiB on Linux.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def snapshot() -> dict[str, int | float | None]:
    mem = cgroup_memory()
    return {
        "pid": os.getpid(),
        "uptime_seconds": round(time.monotonic() - STARTED_AT, 3),
        "process_peak_rss_bytes": process_rss_bytes(),
        "cgroup_memory_current_bytes": mem["current_bytes"],
        "cgroup_memory_limit_bytes": mem["limit_bytes"],
    }


def memory_pressure_pct() -> float | None:
    mem = cgroup_memory()
    current, limit = mem["current_bytes"], mem["limit_bytes"]
    if current is None or limit in (None, 0):
        return None
    return (current / limit) * 100.0
