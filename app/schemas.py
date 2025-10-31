"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl, field_validator


class LinkBase(BaseModel):
    title: str
    description: Optional[str] = None
    url: HttpUrl
    category: str
    color_class: str = "intense-work"
    order_index: int = 0
    is_active: bool = True

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title cannot be empty")
        return value

    @field_validator("category", "color_class", "description", mode="before")
    @classmethod
    def strip_strings(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            return value.strip()
        return value


class LinkCreate(LinkBase):
    pass


class LinkUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[HttpUrl] = None
    category: Optional[str] = None
    color_class: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None
    click_count: Optional[int] = None


class LinkRead(LinkBase):
    id: int
    status: str
    last_checked_at: Optional[datetime] = None
    click_count: int
    last_clicked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LinkClickPayload(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("url cannot be empty")
        return value
