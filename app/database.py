"""Database session and base configuration."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_FILE = Path("data/db.sqlite3")
DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def _ensure_schema() -> None:
    inspector = inspect(engine)
    if "links" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("links")}
    statements = []
    if "click_count" not in existing_columns:
        statements.append("ALTER TABLE links ADD COLUMN click_count INTEGER NOT NULL DEFAULT 0")
    if "last_clicked_at" not in existing_columns:
        statements.append("ALTER TABLE links ADD COLUMN last_clicked_at TIMESTAMP")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


_ensure_schema()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
