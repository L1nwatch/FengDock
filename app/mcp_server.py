"""Authenticated, read-only MCP facade for TriggerToDo and Fire."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sqlite3
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import AnyHttpUrl, Field
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.mcp_auth import PersistentOAuthProvider


provider = PersistentOAuthProvider()
public_host = urlparse(provider.public_url).netloc
read_only = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

mcp = FastMCP(
    name="FengDock",
    instructions=(
        "Read-only access to the owner's TriggerToDo planning data and Fire personal finance data. "
        "Never claim that these tools can create, update, delete, trigger, refresh, or synchronize data."
    ),
    auth_server_provider=provider,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(provider.public_url),
        resource_server_url=AnyHttpUrl(provider.resource_url),
        required_scopes=[provider.scope],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[provider.scope],
            default_scopes=[provider.scope],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[public_host, "localhost:8005", "127.0.0.1:8005"],
        allowed_origins=[provider.public_url],
    ),
)

TRIGGER_URL = os.getenv("TRIGGERTODO_INTERNAL_URL", "http://127.0.0.1:8001").rstrip("/")
TRIGGER_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/triggertodo.db")
FIRE_DATABASE_PATH = Path(
    os.getenv(
        "FIRE_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "vendor" / "fire" / "data" / "fire.sqlite3"),
    )
)


def _trigger_db_path() -> str:
    prefix = "sqlite:///"
    if not TRIGGER_DATABASE_URL.startswith(prefix):
        raise ToolError("TriggerToDo list metadata requires a SQLite database")
    return TRIGGER_DATABASE_URL[len(prefix) :]


def _load_fire_state(loader_name: str) -> dict[str, Any]:
    module_path = Path(__file__).resolve().parents[1] / "vendor" / "fire" / "app" / "db.py"
    spec = importlib.util.spec_from_file_location("fengdock_fire_readonly_db", module_path)
    if not spec or not spec.loader:
        raise ToolError("Fire data readers are currently unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loader = getattr(module, loader_name)
    try:
        with sqlite3.connect(f"file:{FIRE_DATABASE_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return loader(conn)
    except sqlite3.Error as exc:
        raise ToolError("Fire data is currently unavailable") from exc


async def _get_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            clean_params = {key: value for key, value in (params or {}).items() if value is not None}
            response = await client.get(f"{base_url}{path}", params=clean_params)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolError("The internal data service is currently unavailable") from exc


@mcp.custom_route("/login", methods=["GET"])
async def login_page(request: Request) -> Response:
    nonce = request.query_params.get("nonce", "")
    return await provider.get_login_page(nonce)


@mcp.custom_route("/login/callback", methods=["POST"])
async def login_callback(request: Request) -> Response:
    return await provider.handle_login_callback(request)


@mcp.custom_route("/mcp/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"ok": True, "authConfigured": bool(provider.password)})


@mcp.tool(annotations=read_only)
async def list_todo_lists() -> dict[str, Any]:
    """List TriggerToDo task lists. Use this before filtering tasks by list ID."""
    return await asyncio.to_thread(_read_todo_lists)


def _read_todo_lists() -> dict[str, Any]:
    try:
        with sqlite3.connect(f"file:{_trigger_db_path()}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT graph_list_id, display_name FROM todo_list_cache ORDER BY display_name"
            ).fetchall()
    except sqlite3.Error as exc:
        raise ToolError("TriggerToDo list metadata is currently unavailable") from exc
    items = [{"id": row[0], "displayName": row[1]} for row in rows]
    return {"count": len(items), "items": items}


@mcp.tool(annotations=read_only)
async def search_todos(
    query: str | None = Field(default=None, description="Case-insensitive text to find in title or body"),
    pool: str | None = Field(default=None, description="Exact TriggerToDo pool"),
    workflow_status: str | None = Field(default=None, description="Exact workflow status"),
    task_status: Literal["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"] | None = None,
    list_id: str | None = Field(default=None, description="Exact list ID returned by list_todo_lists"),
    limit: int = Field(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Search cached TriggerToDo tasks without synchronizing or modifying them."""
    data = await _get_json(
        TRIGGER_URL,
        "/api/todo/cache/tasks",
        {"pool": pool, "wf_status": workflow_status, "include_deleted": False},
    )
    items = data.get("items", [])
    if query:
        needle = query.casefold()
        items = [item for item in items if needle in f"{item.get('title', '')}\n{item.get('bodyContent', '')}".casefold()]
    if task_status:
        items = [item for item in items if item.get("status") == task_status]
    if list_id:
        items = [item for item in items if item.get("listId") == list_id]
    total = len(items)
    return {"count": total, "returned": min(total, limit), "items": items[:limit]}


@mcp.tool(annotations=read_only)
async def list_trigger_rules() -> dict[str, Any]:
    """List TriggerToDo automation rules; this never runs a trigger."""
    return await _get_json(TRIGGER_URL, "/api/triggers")


@mcp.tool(annotations=read_only)
async def list_trigger_events() -> dict[str, Any]:
    """List TriggerToDo events and whether they have occurred."""
    return await _get_json(TRIGGER_URL, "/api/events")


@mcp.tool(annotations=read_only)
async def list_epics() -> dict[str, Any]:
    """List TriggerToDo epics with status and priority."""
    return await _get_json(TRIGGER_URL, "/api/epics")


@mcp.tool(annotations=read_only)
async def list_milestones() -> dict[str, Any]:
    """List TriggerToDo milestones and their linked planning items."""
    return await _get_json(TRIGGER_URL, "/api/milestones")


@mcp.tool(annotations=read_only)
async def list_scrums(status: Literal["all", "active"] = "all") -> dict[str, Any]:
    """List all TriggerToDo scrums or only the active scrum."""
    return await _get_json(TRIGGER_URL, "/api/scrums/active" if status == "active" else "/api/scrums")


@mcp.tool(annotations=read_only)
async def list_routine_checks(
    start_date: str = Field(description="Inclusive ISO date (YYYY-MM-DD)"),
    end_date: str = Field(description="Inclusive ISO date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """List TriggerToDo routine completion checks in a date range."""
    return await _get_json(
        TRIGGER_URL, "/api/routines/checks", {"start_date": start_date, "end_date": end_date}
    )


@mcp.tool(annotations=read_only)
async def get_finance_overview() -> dict[str, Any]:
    """Read the Fire monthly finance, ledger, forecast, and summary data."""
    return await asyncio.to_thread(_load_fire_state, "load_finance_state")


@mcp.tool(annotations=read_only)
async def get_investments() -> dict[str, Any]:
    """Read the Fire investment snapshots and holdings."""
    return await asyncio.to_thread(_load_fire_state, "load_investment_state")


@mcp.tool(annotations=read_only)
async def get_portfolio() -> dict[str, Any]:
    """Read the Fire portfolio snapshots and holdings."""
    return await asyncio.to_thread(_load_fire_state, "load_portfolio_state")


app = mcp.streamable_http_app()
