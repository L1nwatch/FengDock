"""API routes for managing homepage links."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_session

router = APIRouter(prefix="/links", tags=["links"])


@router.get("/", response_model=List[schemas.LinkRead])
def list_links(
    include_inactive: bool = False,
    ordering: str = Query("order", pattern="^(order|clicks)$"),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    session: Session = Depends(get_session),
) -> List[schemas.LinkRead]:
    return crud.list_links(
        session,
        include_inactive=include_inactive,
        ordering=ordering,
        limit=limit,
    )


@router.get("/{link_id}", response_model=schemas.LinkRead)
def get_link(link_id: int, session: Session = Depends(get_session)) -> schemas.LinkRead:
    link = crud.get_link(session, link_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


@router.post("/", response_model=schemas.LinkRead, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: schemas.LinkCreate,
    session: Session = Depends(get_session),
) -> schemas.LinkRead:
    return crud.create_link(session, payload)


@router.put("/{link_id}", response_model=schemas.LinkRead)
def update_link(
    link_id: int,
    payload: schemas.LinkUpdate,
    session: Session = Depends(get_session),
) -> schemas.LinkRead:
    link = crud.get_link(session, link_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return crud.update_link(session, link, payload)


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(link_id: int, session: Session = Depends(get_session)) -> None:
    link = crud.get_link(session, link_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    crud.delete_link(session, link)


@router.post("/click", status_code=status.HTTP_204_NO_CONTENT)
def register_click(
    payload: schemas.LinkClickPayload,
    session: Session = Depends(get_session),
) -> None:
    link = crud.get_link_by_url(session, payload.url)
    if not link:
        return
    crud.record_link_click(session, link)
