from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("titanbox.audit")


class AuditLog:
    """Append-only JSONL audit log with optional HMAC chaining.

    The chain detects edits inside the file. Durability still depends on the backing storage.
    On Render Free the local file is ephemeral, so records are also emitted to platform logs.
    """

    def __init__(self, path: Path, hmac_key: str | None, max_bytes: int = 5_000_000) -> None:
        self.path = path
        self.key = hmac_key.encode("utf-8") if hmac_key else None
        self.max_bytes = max(100_000, max_bytes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._previous_mac = self._last_mac()

    def _last_mac(self) -> str:
        if not self.path.exists():
            return "0" * 64
        try:
            with self.path.open("rb") as handle:
                lines = handle.readlines()[-20:]
            for raw in reversed(lines):
                try:
                    record = json.loads(raw)
                except Exception:
                    continue
                mac = record.get("mac")
                if isinstance(mac, str) and len(mac) == 64:
                    return mac
        except OSError:
            pass
        return "0" * 64

    def _rotate_if_needed(self) -> None:
        try:
            if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
                return
            rotated = self.path.with_suffix(self.path.suffix + ".1")
            rotated.unlink(missing_ok=True)
            os.replace(self.path, rotated)
            self._previous_mac = "0" * 64
        except OSError:
            log.exception("audit rotation failed")

    def append(
        self,
        *,
        action: str,
        actor_id: int | None,
        result: str,
        project: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._rotate_if_needed()
        record: dict[str, Any] = {
            "ts": int(time.time()),
            "action": action[:80],
            "actor_id": actor_id,
            "result": result[:40],
            "project": project[:64] if project else None,
            "detail": detail or {},
            "prev_mac": self._previous_mac,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if self.key:
            mac = hmac.new(self.key, canonical, hashlib.sha256).hexdigest()
        else:
            mac = hashlib.sha256(canonical).hexdigest()
        record["mac"] = mac
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (line + "\n").encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            self._previous_mac = mac
        except OSError:
            log.exception("audit file append failed")
        # Platform logs provide a second copy (still sanitized by the global log formatter).
        log.info("AUDIT %s", line)
        return record

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = min(max(1, limit), 100)
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                lines = handle.readlines()[-limit:]
        except OSError:
            return []
        records: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def verify(self) -> bool:
        if not self.path.exists():
            return True
        previous = "0" * 64
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    mac = str(record.pop("mac"))
                    if record.get("prev_mac") != previous:
                        return False
                    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                    expected = (
                        hmac.new(self.key, canonical, hashlib.sha256).hexdigest()
                        if self.key
                        else hashlib.sha256(canonical).hexdigest()
                    )
                    if not hmac.compare_digest(mac, expected):
                        return False
                    previous = mac
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False
        return True
