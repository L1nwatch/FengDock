"""API routes for lightweight todo items."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import TodoItem
from ..schemas import TodoItemCreate, TodoItemRead, TodoItemUpdate

router = APIRouter(prefix="/todo", tags=["todo"])


@router.get("/items", response_model=List[TodoItemRead])
def list_todo_items(session: Session = Depends(get_session)) -> List[TodoItemRead]:
    items = (
        session.query(TodoItem)
        .order_by(TodoItem.is_done.asc(), TodoItem.order_index.asc(), TodoItem.created_at.asc())
        .all()
    )
    return items


@router.post("/items", response_model=TodoItemRead, status_code=status.HTTP_201_CREATED)
def create_todo_item(payload: TodoItemCreate, session: Session = Depends(get_session)) -> TodoItemRead:
    item = TodoItem(
        title=payload.title,
        notes=payload.notes,
        is_done=payload.is_done,
        order_index=payload.order_index,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=TodoItemRead)
def update_todo_item(
    item_id: int,
    payload: TodoItemUpdate,
    session: Session = Depends(get_session),
) -> TodoItemRead:
    item = session.query(TodoItem).filter(TodoItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo_item(item_id: int, session: Session = Depends(get_session)) -> None:
    item = session.query(TodoItem).filter(TodoItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo item not found")
    session.delete(item)
    session.commit()
