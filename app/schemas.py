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
    url: HttpUrl
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    color_class: Optional[str] = None
    order_index: Optional[int] = None

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: HttpUrl) -> HttpUrl:
        return value

    @field_validator("title", "description", "category", "color_class", mode="before")
    @classmethod
    def strip_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None
        return value

    @field_validator("order_index")
    @classmethod
    def non_negative_index(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        return max(0, value)


class LoblawsWatchBase(BaseModel):
    url: HttpUrl
    label: Optional[str] = None
    store_id: str = "1032"

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None


class LoblawsWatchCreate(LoblawsWatchBase):
    pass


class LoblawsWatchUpdate(BaseModel):
    label: Optional[str] = None
    store_id: Optional[str] = None

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None


class LoblawsWatchRead(BaseModel):
    id: int
    url: str
    product_code: str
    store_id: str
    label: Optional[str]
    name: Optional[str]
    brand: Optional[str]
    image_url: Optional[str]
    current_price: Optional[float]
    price_unit: Optional[str]
    regular_price: Optional[float]
    sale_text: Optional[str]
    sale_expiry: Optional[datetime]
    sale_type: Optional[str]
    sale_badge_name: Optional[str]
    stock_status: Optional[str]
    last_checked_at: Optional[datetime]
    last_change_at: Optional[datetime]
    last_notified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
