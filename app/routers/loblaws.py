"""Routes for managing Loblaws watchlist and board data."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..auth import require_manage_auth
from ..database import get_session
from ..loblaws import extract_product_code, refresh_all_watches, refresh_single_watch

router = APIRouter(prefix="/loblaws", tags=["loblaws"])


def _serialize_watch(watch: object) -> schemas.LoblawsWatchRead:
    return schemas.LoblawsWatchRead.model_validate(watch)


@router.get("/watches", response_model=List[schemas.LoblawsWatchRead])
def list_watches(session: Session = Depends(get_session)) -> List[schemas.LoblawsWatchRead]:
    watches = crud.list_loblaws_watches(session)
    return [_serialize_watch(watch) for watch in watches]


@router.get("/watches/{watch_id}", response_model=schemas.LoblawsWatchRead)
def get_watch(watch_id: int, session: Session = Depends(get_session)) -> schemas.LoblawsWatchRead:
    watch = crud.get_loblaws_watch(session, watch_id)
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    return _serialize_watch(watch)


@router.post(
    "/watches",
    response_model=schemas.LoblawsWatchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_watch(
    payload: schemas.LoblawsWatchCreate,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.LoblawsWatchRead:
    product_code = extract_product_code(str(payload.url))
    existing = crud.get_loblaws_watch_by_url(session, payload.url)
    if existing:
        await refresh_single_watch(existing.id)
        session.refresh(existing)
        return _serialize_watch(existing)

    watch = crud.create_loblaws_watch(session, payload, product_code)
    await refresh_single_watch(watch.id)
    session.refresh(watch)
    return _serialize_watch(watch)


@router.patch("/watches/{watch_id}", response_model=schemas.LoblawsWatchRead)
async def update_watch(
    watch_id: int,
    payload: schemas.LoblawsWatchUpdate,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.LoblawsWatchRead:
    watch = crud.get_loblaws_watch(session, watch_id)
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    watch = crud.update_loblaws_watch(session, watch, payload)
    await refresh_single_watch(watch.id)
    session.refresh(watch)
    return _serialize_watch(watch)


@router.delete("/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(
    watch_id: int,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> None:
    watch = crud.get_loblaws_watch(session, watch_id)
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    crud.delete_loblaws_watch(session, watch)


@router.post("/watches/{watch_id}/refresh", response_model=schemas.LoblawsWatchRead)
async def refresh_watch_endpoint(
    watch_id: int,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.LoblawsWatchRead:
    updated = await refresh_single_watch(watch_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    watch = crud.get_loblaws_watch(session, watch_id)
    session.refresh(watch)
    return _serialize_watch(watch)


@router.post(
    "/watches/refresh",
    response_model=List[schemas.LoblawsWatchRead],
    status_code=status.HTTP_200_OK,
)
async def refresh_all_endpoint(
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> List[schemas.LoblawsWatchRead]:
    await refresh_all_watches()
    watches = crud.list_loblaws_watches(session)
    for watch in watches:
        session.refresh(watch)
    return [_serialize_watch(watch) for watch in watches]
