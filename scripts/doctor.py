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
        "system": snapshot(),
        "checks": {},
    }
    checks = report["checks"]
    assert isinstance(checks, dict)
    try:
        settings = Settings.from_env()
        settings.validate()
        descriptors = settings.bot_descriptors()
        missing_token_envs: list[str] = []
        for item in descriptors:
            if not isinstance(item, dict):
                continue
            token_env = str(item.get("token_env", "")).strip()
            if token_env and not os.getenv(token_env, "").strip():
                missing_token_envs.append(token_env)
        checks["settings"] = {
            "ok": not missing_token_envs,
            "platform": settings.platform,
            "public_base_url": settings.public_base_url,
            "bot_descriptors": len(descriptors),
            "deploy_admin_ids": sorted(settings.deploy_admin_ids()),
            "missing_token_envs": missing_token_envs,
            "warnings": settings.setup_warnings(),
        }
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
