"""CRUD helpers for link management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def list_links(
    session: Session,
    *,
    include_inactive: bool = False,
    ordering: str = "order",
    limit: Optional[int] = None,
) -> List[models.Link]:
    statement = select(models.Link)
    if not include_inactive:
        statement = statement.where(models.Link.is_active.is_(True))
    if ordering == "clicks":
        statement = statement.order_by(
            models.Link.click_count.desc(),
            models.Link.last_clicked_at.desc(),
            models.Link.order_index,
            models.Link.id,
        )
    else:
        statement = statement.order_by(models.Link.order_index, models.Link.id)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def get_link(session: Session, link_id: int) -> Optional[models.Link]:
    return session.get(models.Link, link_id)


def get_link_by_url(session: Session, url: str) -> Optional[models.Link]:
    normalized = url.strip()
    candidates = {normalized}
    if normalized.endswith("/"):
        candidates.add(normalized.rstrip("/"))
    else:
        candidates.add(f"{normalized}/")
    statement = select(models.Link).where(models.Link.url.in_(candidates))
    return session.scalars(statement).first()


def create_link(session: Session, payload: schemas.LinkCreate) -> models.Link:
    link = models.Link(**payload.model_dump())
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def update_link(session: Session, link: models.Link, payload: schemas.LinkUpdate) -> models.Link:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(link, field, value)
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def delete_link(session: Session, link: models.Link) -> None:
    session.delete(link)
    session.commit()


def record_link_click(session: Session, link: models.Link) -> None:
    link.click_count = (link.click_count or 0) + 1
    link.last_clicked_at = datetime.now(timezone.utc)
    session.add(link)
    session.commit()


def bulk_update_status(
    session: Session,
    updates: Iterable[tuple[int, str]],
) -> None:
    for link_id, status in updates:
        link = session.get(models.Link, link_id)
        if not link:
            continue
        link.mark_checked(status)
        session.add(link)
    session.commit()


def list_loblaws_watches(session: Session) -> List[models.LoblawsWatch]:
    statement = select(models.LoblawsWatch).order_by(models.LoblawsWatch.id)
    return list(session.scalars(statement))


def get_loblaws_watch(session: Session, watch_id: int) -> Optional[models.LoblawsWatch]:
    return session.get(models.LoblawsWatch, watch_id)


def get_loblaws_watch_by_url(session: Session, url: str) -> Optional[models.LoblawsWatch]:
    normalized = str(url).strip()
    statement = (
        select(models.LoblawsWatch)
        .where(models.LoblawsWatch.url == normalized)
        .limit(1)
    )
    return session.scalars(statement).first()


def create_loblaws_watch(
    session: Session, payload: schemas.LoblawsWatchCreate, product_code: str
) -> models.LoblawsWatch:
    normalized_url = str(payload.url).strip()
    watch = models.LoblawsWatch(
        url=normalized_url,
        product_code=product_code,
        store_id=payload.store_id,
        label=payload.label,
    )
    session.add(watch)
    session.commit()
    session.refresh(watch)
    return watch


def update_loblaws_watch(
    session: Session,
    watch: models.LoblawsWatch,
    payload: schemas.LoblawsWatchUpdate,
) -> models.LoblawsWatch:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(watch, field, value)
    session.add(watch)
    session.commit()
    session.refresh(watch)
    return watch


def delete_loblaws_watch(session: Session, watch: models.LoblawsWatch) -> None:
    session.delete(watch)
    session.commit()
