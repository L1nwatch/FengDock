"""Loblaws product monitoring helpers."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from urllib.parse import urlparse

import httpx
from zoneinfo import ZoneInfo

from . import crud, models
from .database import session_scope
from .notifications import send_notification

logger = logging.getLogger(__name__)

API_BASE = "https://api.pcexpress.ca/pcx-bff/api"
API_KEY = os.getenv("LOBLAWS_API_KEY", "C1xujSegT5j3ap3yexJjqhOfELwGKYvz")
DEFAULT_STORE_ID = os.getenv("LOBLAWS_DEFAULT_STORE", "1032")
DEFAULT_BANNER = os.getenv("LOBLAWS_BANNER", "loblaw")
DEFAULT_LANG = os.getenv("LOBLAWS_LANG", "en")
DEFAULT_PICKUP = os.getenv("LOBLAWS_PICKUP_TYPE", "STORE")

try:
    TORONTO_TZ = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - fallback when tzdata missing
    TORONTO_TZ = timezone.utc

_PRODUCT_CODE_RE = re.compile(r"/p/([^/?#]+)", re.IGNORECASE)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class WatchTarget:
    id: int
    product_code: str
    store_id: str
    url: str
    label: Optional[str]


@dataclass
class ProductSnapshot:
    watch_id: int
    payload: Optional[dict]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.payload is not None


def extract_product_code(url: str) -> str:
    """Extract product code from a Loblaws PDP URL."""

    match = _PRODUCT_CODE_RE.search(url)
    if not match:
        raise ValueError("未能从链接中提取商品编号，请确认链接中包含 /p/<code>")
    code = match.group(1).split("?")[0].strip()
    if not code:
        raise ValueError("解析到的商品编号为空")
    return code.upper()


def _current_date_param() -> str:
    now_local = datetime.now(TORONTO_TZ)
    return now_local.strftime("%d%m%Y")


def _build_headers() -> dict[str, str]:
    return {
        "x-apikey": API_KEY,
        "accept": "application/json, text/plain, */*",
        "user-agent": _USER_AGENT,
        "referer": "https://www.loblaws.ca/",
    }


async def fetch_product_payload(
    product_code: str,
    *,
    store_id: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    params = {
        "lang": DEFAULT_LANG,
        "date": _current_date_param(),
        "pickupType": DEFAULT_PICKUP,
        "storeId": store_id or DEFAULT_STORE_ID,
        "banner": DEFAULT_BANNER,
    }
    url = f"{API_BASE}/v1/products/{product_code}"
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15)
        close_client = True
    try:
        response = await client.get(url, params=params, headers=_build_headers())
        response.raise_for_status()
    finally:
        if close_client:
            await client.aclose()
    return response.json()


async def refresh_watch_ids(watch_ids: Optional[Iterable[int]] = None) -> List[int]:
    targets = await _load_targets(watch_ids)
    if not targets:
        return []

    snapshots: List[ProductSnapshot] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for target in targets:
            try:
                payload = await fetch_product_payload(
                    target.product_code, store_id=target.store_id, client=client
                )
                snapshots.append(ProductSnapshot(watch_id=target.id, payload=payload))
            except Exception as exc:  # pragma: no cover - network failures
                logger.warning(
                    "Failed to fetch product %s for watch %s: %s",
                    target.product_code,
                    target.id,
                    exc,
                )
                snapshots.append(
                    ProductSnapshot(watch_id=target.id, payload=None, error=str(exc))
                )
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.2)  # polite pacing

    updated_ids = await asyncio.to_thread(_apply_snapshots, snapshots)
    return updated_ids


async def refresh_all_watches() -> List[int]:
    return await refresh_watch_ids()


async def refresh_single_watch(watch_id: int) -> Optional[int]:
    updated = await refresh_watch_ids([watch_id])
    return updated[0] if updated else None


async def _load_targets(watch_ids: Optional[Iterable[int]]) -> List[WatchTarget]:
    def inner() -> List[WatchTarget]:
        with session_scope() as session:
            watches = crud.list_loblaws_watches(session)
            results: List[WatchTarget] = []
            for watch in watches:
                if watch_ids and watch.id not in watch_ids:
                    continue
                results.append(
                    WatchTarget(
                        id=watch.id,
                        product_code=watch.product_code,
                        store_id=watch.store_id or DEFAULT_STORE_ID,
                        url=watch.url,
                        label=watch.label,
                    )
                )
            return results

    return await asyncio.to_thread(inner)


def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TORONTO_TZ)
    return dt.astimezone(timezone.utc)


def _select_primary_offer(payload: dict) -> Optional[dict]:
    offers = payload.get("offers") or []
    if not offers:
        return None
    # Prefer an offer with a deal badge to highlight promotions.
    for offer in offers:
        badges = (offer.get("badges") or {}).get("dealBadge")
        if badges:
            return offer
    return offers[0]


def _extract_image(payload: dict) -> Optional[str]:
    assets = payload.get("imageAssets") or []
    for asset in assets:
        for key in ("largeUrl", "extraLargeUrl", "mediumUrl"):
            url = asset.get(key)
            if url:
                return url
    return None


def _apply_snapshots(snapshots: List[ProductSnapshot]) -> List[int]:
    now = datetime.now(timezone.utc)
    updated_ids: List[int] = []

    with session_scope() as session:
        for snapshot in snapshots:
            watch = session.get(models.LoblawsWatch, snapshot.watch_id)
            if not watch:
                continue
            watch.last_checked_at = now
            updated_ids.append(watch.id)

            if not snapshot.ok:
                logger.debug(
                    "No payload for watch %s, keeping previous state", watch.id
                )
                continue

            payload = snapshot.payload or {}
            offer = _select_primary_offer(payload)
            price_block = (offer or {}).get("price") or {}
            was_price_block = (offer or {}).get("wasPrice") or {}
            badges = (offer or {}).get("badges") or {}
            deal_badge = badges.get("dealBadge") or {}

            current_price = price_block.get("value")
            price_unit = price_block.get("unit")
            regular_price = was_price_block.get("value")
            sale_text = deal_badge.get("text")
            sale_type = price_block.get("type") or deal_badge.get("type")
            sale_expiry = _parse_expiry(
                deal_badge.get("expiryDate") or price_block.get("expiryDate")
            )
            stock_status = (offer or {}).get("stockStatus")

            signature_parts = [
                sale_type or "NONE",
                sale_text or "",
                sale_expiry.isoformat() if sale_expiry else "",
                f"{current_price:.2f}" if isinstance(current_price, (int, float)) else "",
                f"{regular_price:.2f}" if isinstance(regular_price, (int, float)) else "",
                stock_status or "",
            ]
            signature = "|".join(signature_parts)
            changed = signature != (watch.last_signature or "")

            watch.name = payload.get("name") or watch.name
            watch.brand = payload.get("brand") or watch.brand
            watch.image_url = _extract_image(payload) or watch.image_url
            watch.current_price = float(current_price) if current_price is not None else None
            watch.price_unit = price_unit
            watch.regular_price = (
                float(regular_price) if regular_price is not None else None
            )
            watch.sale_text = sale_text
            watch.sale_type = sale_type
            watch.sale_badge_name = deal_badge.get("name") if deal_badge else None
            watch.sale_expiry = sale_expiry
            watch.stock_status = stock_status
            watch.last_signature = signature
            if changed:
                watch.last_change_at = now

            deal_active = bool(deal_badge)
            should_notify = changed and deal_active
            if should_notify:
                title = watch.label or watch.name or watch.product_code
                parts = []
                if sale_text:
                    parts.append(sale_text)
                elif sale_type:
                    parts.append(sale_type.title())
                if watch.current_price is not None:
                    parts.append(
                        f"Now ${watch.current_price:.2f}/{watch.price_unit or 'ea'}"
                    )
                if watch.regular_price is not None:
                    parts.append(f"Was ${watch.regular_price:.2f}")
                if sale_expiry:
                    local_expiry = sale_expiry.astimezone(TORONTO_TZ)
                    parts.append(
                        "Exp. " + local_expiry.strftime("%Y-%m-%d")
                    )
                if stock_status:
                    parts.append(stock_status.title())
                message = " | ".join(parts) if parts else "Sale update"
                send_notification(title, message, link=watch.url)
                watch.last_notified_at = now

            session.add(watch)

    return updated_ids
