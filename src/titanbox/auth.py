from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .settings import Settings


def secure_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode(), right.encode())


def require_admin_token(settings: Settings, authorization: str | None) -> None:
    if not settings.admin_api_enabled or not settings.admin_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secure_equal(token, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


def admin_guard(settings: Settings):
    async def guard(authorization: str | None = Header(default=None)) -> None:
        require_admin_token(settings, authorization)

    return guard
