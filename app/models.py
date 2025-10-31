"""Database models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class Link(Base):
    """Bookmark style link displayed on the homepage."""

    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(512), nullable=False, unique=True)
    category = Column(String(50), nullable=False)
    color_class = Column(String(50), nullable=False, default="intense-work")
    order_index = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="unknown")
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def mark_checked(self, status: str) -> None:
        self.status = status
        self.last_checked_at = datetime.now(timezone.utc)


class LoblawsWatch(Base):
    """Tracked Loblaws product with latest sale information."""

    __tablename__ = "loblaws_watches"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(512), nullable=False, unique=True)
    product_code = Column(String(64), nullable=False, index=True)
    store_id = Column(String(16), nullable=False, default="1032")
    label = Column(String(120), nullable=True)
    name = Column(String(200), nullable=True)
    brand = Column(String(120), nullable=True)
    image_url = Column(String(512), nullable=True)
    current_price = Column(Float, nullable=True)
    price_unit = Column(String(32), nullable=True)
    regular_price = Column(Float, nullable=True)
    sale_text = Column(String(160), nullable=True)
    sale_expiry = Column(DateTime(timezone=True), nullable=True)
    sale_type = Column(String(32), nullable=True)
    sale_badge_name = Column(String(64), nullable=True)
    stock_status = Column(String(32), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_change_at = Column(DateTime(timezone=True), nullable=True)
    last_notified_at = Column(DateTime(timezone=True), nullable=True)
    last_signature = Column(String(200), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
