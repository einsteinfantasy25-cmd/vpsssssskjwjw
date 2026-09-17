from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

_SECRET_NAME_HINTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "DSN",
)
_TELEGRAM_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])\d{5,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_])")
_URL_CREDENTIAL_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<creds>[^/@\s:]+:[^/@\s]+)@")


class SecretRedactor:
    """Best-effort log redaction for exact environment secrets and common token shapes.

    Redaction is defense-in-depth. The primary rule remains: never intentionally log a secret.
    """

    def __init__(self, values: Iterable[str] = ()) -> None:
        self._values: tuple[str, ...] = ()
        self.refresh(values)

    @staticmethod
    def _discover_environment_secrets() -> list[str]:
        values: list[str] = []
        for key, value in os.environ.items():
            upper = key.upper()
            if not value or len(value) < 6:
                continue
            if any(hint in upper for hint in _SECRET_NAME_HINTS):
                values.append(value)
        return values

    def refresh(self, extra_values: Iterable[str] = ()) -> None:
        values = set(self._discover_environment_secrets())
        values.update(v for v in extra_values if v and len(v) >= 6)
        # Longest first so a shorter secret cannot expose the suffix of a longer one.
        self._values = tuple(sorted(values, key=len, reverse=True))

    def redact(self, value: object) -> str:
        text = str(value)
        for secret in self._values:
            text = text.replace(secret, "<redacted>")
        text = _TELEGRAM_TOKEN_RE.sub("<redacted-telegram-token>", text)
        text = _URL_CREDENTIAL_RE.sub(lambda m: f"{m.group('scheme')}<redacted>@", text)
        return text


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str, redactor: SecretRedactor) -> None:
        super().__init__(fmt)
        self.redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self.redactor.redact(super().format(record))


def configure_logging(level: str, *, extra_secrets: Iterable[str] = ()) -> SecretRedactor:
    redactor = SecretRedactor(extra_secrets)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", redactor)
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    return redactor


class TokenBucket:
    """Small async token bucket used to contain noisy bots without unbounded state."""

    def __init__(self, rate_per_minute: int, burst: int) -> None:
        self.rate_per_second = max(1, rate_per_minute) / 60.0
        self.capacity = float(max(1, burst))
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        async with self._lock:
            elapsed = max(0.0, now - self.updated)
            self.updated = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
            if self.tokens < cost:
                return False
            self.tokens -= cost
            return True


@dataclass(slots=True)
class FailureCircuit:
    threshold: int
    window_seconds: float
    cooldown_seconds: float
    _failures: deque[float] = field(default_factory=deque)
    _open_until: float = 0.0

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] > self.window_seconds:
            self._failures.popleft()

    def retry_after(self) -> int:
        now = time.monotonic()
        if self._open_until and self._open_until <= now:
            # A completed cooldown starts a clean observation window instead of immediately
            # re-opening because of stale failures from before the cooldown.
            self._open_until = 0.0
            self._failures.clear()
            return 0
        if self._open_until <= now:
            return 0
        return max(1, int(self._open_until - now + 0.999))

    def is_open(self) -> bool:
        return self.retry_after() > 0

    def record_failure(self) -> None:
        now = time.monotonic()
        self._prune(now)
        self._failures.append(now)
        if len(self._failures) >= self.threshold:
            self._open_until = max(self._open_until, now + self.cooldown_seconds)

    def record_success(self) -> None:
        now = time.monotonic()
        self._prune(now)
        # A successful request proves the handler can make progress. Keep only recent failures,
        # but do not clear an already-open cooldown early.
        if not self.is_open() and self._failures:
            self._failures.popleft()

    def recent_failures(self) -> int:
        now = time.monotonic()
        self._prune(now)
        return len(self._failures)


def _decode_base32(secret: str) -> bytes:
    normalized = "".join(secret.split()).upper().rstrip("=")
    if not normalized:
        raise ValueError("TOTP secret is empty")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        return base64.b32decode(normalized + padding, casefold=True)
    except Exception as exc:  # binascii.Error differs across Python versions
        raise ValueError("TOTP secret must be valid Base32") from exc


def totp_code(secret: str, *, unix_time: float | None = None, step_seconds: int = 30, digits: int = 6) -> str:
    key = _decode_base32(secret)
    counter = int((time.time() if unix_time is None else unix_time) // step_seconds)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def verify_totp(
    secret: str,
    code: str,
    *,
    unix_time: float | None = None,
    step_seconds: int = 30,
    window: int = 1,
    last_counter: int | None = None,
) -> int | None:
    if not (code.isdigit() and len(code) == 6):
        return None
    now = time.time() if unix_time is None else unix_time
    current = int(now // step_seconds)
    key = _decode_base32(secret)
    for delta in range(-window, window + 1):
        counter = current + delta
        if counter < 0 or (last_counter is not None and counter <= last_counter):
            continue
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        expected = str(value % 1_000_000).zfill(6)
        if hmac.compare_digest(expected, code):
            return counter
    return None
