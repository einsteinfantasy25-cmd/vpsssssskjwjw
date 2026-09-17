#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import secrets
import urllib.parse


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Base32 TOTP secret for TitanBox Deploy Admin")
    parser.add_argument("--account", default="titanbox-admin", help="Label shown in the authenticator app")
    parser.add_argument("--issuer", default="TitanBox", help="Authenticator issuer label")
    args = parser.parse_args()

    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    label = urllib.parse.quote(f"{args.issuer}:{args.account}")
    issuer = urllib.parse.quote(args.issuer)
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    print("DEPLOY_TOTP_SECRET=" + secret)
    print("Authenticator URI=" + uri)
    print("Keep the secret private. Do not commit it to GitHub or send it in Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
