"""CRUD helpers for link management."""

from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def list_links(session: Session, *, include_inactive: bool = False) -> List[models.Link]:
    statement = select(models.Link)
    if not include_inactive:
        statement = statement.where(models.Link.is_active.is_(True))
    statement = statement.order_by(models.Link.order_index, models.Link.id)
    return list(session.scalars(statement))


def get_link(session: Session, link_id: int) -> Optional[models.Link]:
    return session.get(models.Link, link_id)


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
