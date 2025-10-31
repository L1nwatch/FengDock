"""APScheduler integration for background jobs."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, List, Tuple

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import crud
from .database import session_scope

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")
CHECK_INTERVAL_MINUTES = int(os.getenv("LINK_CHECK_INTERVAL_MINUTES", "30"))


async def _fetch_active_links() -> List[Tuple[int, str]]:
    def inner() -> List[Tuple[int, str]]:
        with session_scope() as session:
            return [(link.id, link.url) for link in crud.list_links(session)]

    return await asyncio.to_thread(inner)


async def _persist_status(updates: Iterable[Tuple[int, str]]) -> None:
    def inner() -> None:
        with session_scope() as session:
            crud.bulk_update_status(session, updates)

    await asyncio.to_thread(inner)


async def run_link_health_check() -> None:
    links = await _fetch_active_links()
    if not links:
        logger.debug("No links to check during health job")
        return

    updates: List[Tuple[int, str]] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for link_id, url in links:
            status = "down"
            try:
                response = await client.head(url, follow_redirects=True)
                if response.status_code < 400:
                    status = "up"
                elif response.status_code < 500:
                    status = "degraded"
                else:
                    status = "down"
            except httpx.HTTPError as exc:  # pragma: no cover - network errors
                logger.warning("Health check failed for %s: %s", url, exc)
                status = "error"
            updates.append((link_id, status))

    await _persist_status(updates)
    logger.info("Health check updated %d links", len(updates))


def configure_jobs() -> None:
    if scheduler.get_job("link_health_check"):
        return

    scheduler.add_job(
        run_link_health_check,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="link_health_check",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def start_scheduler() -> None:
    configure_jobs()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


async def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
