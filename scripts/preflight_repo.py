#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "Dockerfile",
    "render.yaml",
    "requirements.txt",
    "src/titanbox/main.py",
    "src/titanbox/settings.py",
    "src/titanbox/telegram.py",
    "src/titanbox/security.py",
    "src/titanbox/audit.py",
    "src/titanbox/storage.py",
    "src/titanbox/database.py",
    "src/titanbox/infrastructure.py",
    "src/titanbox/plugins/deploy_admin.py",
    "scripts/entrypoint.sh",
    "scripts/generate_totp.py",
    "scripts/secret_scan.py",
    "scripts/wake_render.py",
    "config/apps.toml",
    "nginx/nginx.conf.template",
]


def main() -> int:
    missing = [rel for rel in REQUIRED if not ROOT.joinpath(rel).exists()]
    report = {
        "root": str(ROOT),
        "required_count": len(REQUIRED),
        "missing": missing,
        "ok": not missing,
    }
    print(json.dumps(report, indent=2))
    if missing:
        print("\nFATAL: repository upload is incomplete.", file=sys.stderr)
        print("Upload the FULL TitanBox project root to GitHub, including src/, config/, scripts/, nginx/.", file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
