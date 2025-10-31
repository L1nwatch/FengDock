"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


def create_app() -> FastAPI:
    app = FastAPI(title="FengDock API", lifespan=lifespan)

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        return {"message": "FengDock backend is running"}

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(links.router)

    return app


app = create_app()
