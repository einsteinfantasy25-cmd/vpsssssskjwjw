#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from titanbox.settings import Settings  # noqa: E402
from titanbox.system_metrics import snapshot  # noqa: E402


def check_write(path: Path) -> dict[str, object]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix="titanbox-doctor-", delete=True):
            pass
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "platform_hint": "render" if os.getenv("RENDER") else "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "generic",
        "system": snapshot(),
        "checks": {},
    }
    checks = report["checks"]
    assert isinstance(checks, dict)
    try:
        settings = Settings.from_env()
        settings.validate()
        checks["settings"] = {"ok": True, "bot_descriptors": len(settings.bot_descriptors())}
        checks["deploy_root_writable"] = check_write(settings.deploy_root)
    except Exception as exc:
        checks["settings"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    checks["tmp_writable"] = check_write(Path("/tmp"))
    checks["workspace_writable"] = check_write(Path("/workspace"))
    try:
        socket.getaddrinfo("api.telegram.org", 443)
        checks["telegram_dns"] = {"ok": True}
    except OSError as exc:
        checks["telegram_dns"] = {"ok": False, "error": str(exc)}

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(v.get("ok") for v in checks.values() if isinstance(v, dict)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
