"""Simple notification helper for board alerts."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT_ENV = "LOBLAWS_NOTIFY_ENDPOINT"


def send_notification(title: str, message: str, *, link: Optional[str] = None) -> None:
    """Send a push-style notification via an HTTP endpoint.

    If the ``LOBLAWS_NOTIFY_ENDPOINT`` environment variable is not configured, the
    notification is logged instead so callers always get signal in the logs.

    The endpoint is treated as an ``ntfy`` compatible URL: the request is sent as
    plain text with an optional ``Title`` and ``Click`` header.
    """

    endpoint = os.getenv(_ENDPOINT_ENV)
    if not endpoint:
        logger.info("[notify] %s -- %s", title, message)
        return

    headers = {"Title": title}
    if link:
        headers["Click"] = link

    try:
        response = httpx.post(endpoint, content=message.encode("utf-8"), headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - best effort notification
        logger.warning("Failed to send notification to %s: %s", endpoint, exc)
