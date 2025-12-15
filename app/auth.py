"""Authentication helpers for protected pages and APIs."""

from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import HTTPException, Request, status


def require_manage_auth(request: Request) -> None:
    expected_hash = os.getenv("PRIVATE_PAGE_PASSWORD_HASH")
    if not expected_hash:
        return
    password = (
        request.query_params.get("token")
        or request.headers.get("X-Private-Token")
        or request.headers.get("X-Loblaws-Token")
    )
    if not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    token_hash = password.strip().lower()
    if len(token_hash) != 64 or not all(c in "0123456789abcdef" for c in token_hash):
        token_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    if not secrets.compare_digest(token_hash, expected_hash.lower()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
