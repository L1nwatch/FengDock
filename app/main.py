"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import links
from .scheduler import run_link_health_check, shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    asyncio.create_task(run_link_health_check())
    try:
        yield
    finally:
        await shutdown_scheduler()


FRONTEND_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = FRONTEND_ROOT / "index.html"
STATIC_DIR = FRONTEND_ROOT / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="FengDock API", lifespan=lifespan)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root() -> str:
        try:
            return INDEX_FILE.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=404, detail="Homepage not configured") from exc

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(links.router)

    return app


app = create_app()
