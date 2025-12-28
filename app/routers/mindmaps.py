"""Routes for shared mind-map documents."""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..auth import require_manage_auth
from ..database import get_session

router = APIRouter(prefix="/mindmaps", tags=["mindmaps"])


def _serialize_doc(doc: object) -> schemas.MindMapDocRead:
    if isinstance(doc, schemas.MindMapDocRead):
        return doc
    data = json.loads(doc.data_json)
    return schemas.MindMapDocRead(
        id=doc.id,
        title=doc.title,
        data=data,
        version=doc.version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/", response_model=List[schemas.MindMapDocListItem])
def list_docs(
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> List[schemas.MindMapDocListItem]:
    docs = crud.list_mindmap_docs(session)
    return [
        schemas.MindMapDocListItem(
            id=doc.id,
            title=doc.title,
            version=doc.version,
            updated_at=doc.updated_at,
        )
        for doc in docs
    ]


@router.get("/{doc_id}", response_model=schemas.MindMapDocRead)
def get_doc(
    doc_id: int,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.MindMapDocRead:
    doc = crud.get_mindmap_doc(session, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    return _serialize_doc(doc)


@router.post("/", response_model=schemas.MindMapDocRead, status_code=status.HTTP_201_CREATED)
def create_doc(
    payload: schemas.MindMapDocCreate,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.MindMapDocRead:
    doc = crud.create_mindmap_doc(session, payload)
    return _serialize_doc(doc)


@router.put("/{doc_id}", response_model=schemas.MindMapDocRead)
def update_doc(
    doc_id: int,
    payload: schemas.MindMapDocUpdate,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> schemas.MindMapDocRead:
    doc = crud.get_mindmap_doc(session, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    if (
        payload.expected_version is not None
        and payload.expected_version != doc.version
        and not payload.force
    ):
        current = _serialize_doc(doc)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "message": "Version conflict",
                "current": current.model_dump(),
            },
        )
    doc = crud.update_mindmap_doc(session, doc, payload, force=payload.force)
    return _serialize_doc(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(
    doc_id: int,
    session: Session = Depends(get_session),
    _auth: None = Depends(require_manage_auth),
) -> None:
    doc = crud.get_mindmap_doc(session, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    session.delete(doc)
    session.commit()
