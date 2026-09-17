#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

_TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Wake/check TitanBox on demand. Retries only for this one command while a cold "
            "start is in progress; it is not a keepalive loop."
        )
    )
    parser.add_argument("base_url", help="Example: https://titanbox.onrender.com")
    parser.add_argument("--timeout", type=float, default=90.0, help="Total seconds to wait (default: 90)")
    parser.add_argument("--interval", type=float, default=2.0, help="Retry interval in seconds (default: 2)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if not base.startswith("https://"):
        parser.error("base_url must use HTTPS")
    if args.timeout < 1 or args.timeout > 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    if args.interval < 0.5 or args.interval > 30:
        parser.error("--interval must be between 0.5 and 30 seconds")

    url = base + "/wakez"
    started = time.monotonic()
    deadline = started + args.timeout
    attempt = 0
    last_error = "unknown"

    while time.monotonic() < deadline:
        attempt += 1
        remaining = max(1.0, deadline - time.monotonic())
        request_timeout = min(15.0, remaining)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "TitanBox-Wake/1.0", "Cache-Control": "no-cache"},
        )
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                body = response.read(200_000)
                elapsed = time.monotonic() - started
                if 200 <= response.status < 300:
                    print(f"Awake: HTTP {response.status} in {elapsed:.1f}s ({attempt} attempt(s))")
                    try:
                        print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
                    except Exception:
                        print(body.decode("utf-8", "replace"))
                    return 0
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in _TRANSIENT_HTTP:
                print(f"Wake failed: non-retryable {last_error}")
                return 1
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))

    elapsed = time.monotonic() - started
    print(f"Wake failed after {elapsed:.1f}s and {attempt} attempt(s): {last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
