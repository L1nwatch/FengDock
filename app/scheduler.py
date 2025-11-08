"""APScheduler integration for background jobs."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, List, Tuple

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import crud
from .loblaws import refresh_all_watches
from .database import session_scope

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None
CHECK_INTERVAL_MINUTES = int(os.getenv("LINK_CHECK_INTERVAL_MINUTES", "30"))
LOBLAWS_INTERVAL_MINUTES = int(os.getenv("LOBLAWS_REFRESH_INTERVAL_MINUTES", "60"))


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


async def run_loblaws_refresh_job() -> None:
    updated = await refresh_all_watches()
    if updated:
        logger.info("Loblaws refresh updated %d products", len(updated))
    else:
        logger.debug("Loblaws refresh found no products to update")


def _ensure_scheduler() -> AsyncIOScheduler:
    """Recreate scheduler when its bound loop is gone (common in tests)."""

    global scheduler
    loop = asyncio.get_running_loop()
    existing_loop = getattr(scheduler, "_eventloop", None)

    if scheduler is None or existing_loop is None or existing_loop.is_closed():
        scheduler = AsyncIOScheduler(timezone="UTC", event_loop=loop)
        return scheduler

    if existing_loop is not loop:
        try:
            scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover - defensive cleanup
            logger.debug("Failed to shutdown old scheduler", exc_info=True)
        scheduler = AsyncIOScheduler(timezone="UTC", event_loop=loop)
        return scheduler

    return scheduler


def configure_jobs(current_scheduler: AsyncIOScheduler) -> None:
    if current_scheduler.get_job("link_health_check"):
        current_scheduler.remove_job("link_health_check")

    current_scheduler.add_job(
        run_link_health_check,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="link_health_check",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    if current_scheduler.get_job("loblaws_refresh"):
        current_scheduler.remove_job("loblaws_refresh")

    current_scheduler.add_job(
        run_loblaws_refresh_job,
        "interval",
        minutes=LOBLAWS_INTERVAL_MINUTES,
        id="loblaws_refresh",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def start_scheduler() -> None:
    current_scheduler = _ensure_scheduler()
    configure_jobs(current_scheduler)
    if not current_scheduler.running:
        current_scheduler.start()
        logger.info("Scheduler started")


async def shutdown_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
    scheduler = None
