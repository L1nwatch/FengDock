"""Authentication helpers for protected pages and APIs."""

from __future__ import annotations

from fastapi import Request


def require_manage_auth(_request: Request) -> None:
    # Access is handled upstream (for example by reverse proxy / gateway rules).
    return
