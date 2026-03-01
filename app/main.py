"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_manage_auth
from .database import Base, engine
from .routers import links, loblaws, mindmaps
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
TOOLS_DIR = FRONTEND_ROOT / "tools"
STATIC_DIR = FRONTEND_ROOT / "static"
BOARD_FILE = TOOLS_DIR / "loblaws-board.html"
BOARD_MANAGE_FILE = TOOLS_DIR / "loblaws-manage.html"


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

    @app.get("/tools/json-viewer", response_class=HTMLResponse, include_in_schema=False)
    async def json_viewer() -> str:
        json_viewer_file = TOOLS_DIR / "json-viewer.html"
        try:
            return json_viewer_file.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=404, detail="JSON viewer not available") from exc

    @app.get("/board", response_class=HTMLResponse, include_in_schema=False)
    async def loblaws_board() -> str:
        try:
            return BOARD_FILE.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=404, detail="Board not available") from exc

    @app.get("/board/manage", response_class=HTMLResponse, include_in_schema=False)
    async def loblaws_board_manage(
        _credentials: None = Depends(require_manage_auth),
    ) -> str:
        try:
            return BOARD_MANAGE_FILE.read_text(encoding="utf-8")
        except FileNotFoundError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=404, detail="Board manager not available") from exc

    @app.head("/tools/json-viewer", include_in_schema=False)
    async def json_viewer_head() -> Response:
        return Response(status_code=200)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(links.router)
    app.include_router(links.router, prefix="/api")
    app.include_router(loblaws.router)
    app.include_router(mindmaps.router)
    app.include_router(mindmaps.router, prefix="/api")

    return app


app = create_app()
