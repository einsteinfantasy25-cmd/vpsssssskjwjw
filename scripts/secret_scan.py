#!/usr/bin/env python3
"""Small dependency-free repository secret scanner for CI/preflight.

This is intentionally conservative: it catches obvious high-impact credentials that should
never be committed. It complements, not replaces, GitHub/provider secret scanning.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "node_modules"}
SKIP_NAMES = {"MANIFEST.sha256"}
TEXT_SUFFIXES = {
    "", ".py", ".toml", ".yaml", ".yml", ".json", ".md", ".txt", ".sh", ".env",
    ".ini", ".cfg", ".conf", ".example", ".dockerignore", ".gitignore",
}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Telegram bot token", re.compile(r"(?<![A-Za-z0-9_])\d{5,}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_])")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # Scan known text files and extensionless project/config files only.
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        yield path


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                line_text = text.splitlines()[line - 1] if text.splitlines() else ""
                if "secret-scan: allow-test-fixture" in line_text:
                    continue
                findings.append(f"{path.relative_to(ROOT)}:{line}: possible {label}")
    if findings:
        print("Secret scan FAILED. Remove/revoke the credential before committing:")
        print("\n".join(findings))
        return 1
    print("Secret scan OK: no obvious committed credentials found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
