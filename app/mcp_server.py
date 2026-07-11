"""Authenticated, read-only MCP facade for TriggerToDo and Fire."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sqlite3
from datetime import date
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


def _iso_date(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolError(f"{field_name} must be an ISO date (YYYY-MM-DD)") from None


def _month_label(value: str | None) -> str | None:
    if value is None:
        return None
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ToolError("month must use YYYY-MM")
    return value


def _limit_finance_state(
    state: dict[str, Any],
    *,
    month: str | None,
    months_limit: int,
    ledger_start_date: str | None,
    ledger_end_date: str | None,
    ledger_limit: int,
    include_forecast: bool,
    forecast_limit: int,
) -> dict[str, Any]:
    selected_month = _month_label(month)
    start = _iso_date(ledger_start_date, "ledger_start_date")
    end = _iso_date(ledger_end_date, "ledger_end_date")
    if start and end and start > end:
        raise ToolError("ledger_start_date must not be after ledger_end_date")

    all_months = state.get("months", [])
    months = [item for item in all_months if item.get("label") == selected_month] if selected_month else all_months
    months = months[:months_limit]
    returned_labels = {str(item.get("label", "")) for item in months}

    all_ledger = state.get("ledger", [])
    ledger = all_ledger
    if start:
        ledger = [item for item in ledger if str(item.get("date", "")) >= start]
    if end:
        ledger = [item for item in ledger if str(item.get("date", "")) <= end]
    if not start and not end:
        if selected_month:
            ledger = [item for item in ledger if str(item.get("date", ""))[:7] == selected_month]
        elif returned_labels:
            ledger = [item for item in ledger if str(item.get("date", ""))[:7] in returned_labels]
    ledger_total = len(ledger)
    ledger = ledger[:ledger_limit]

    all_forecast = state.get("forecast", [])
    forecast = all_forecast[:forecast_limit] if include_forecast else []
    return {
        "months": months,
        "ledger": ledger,
        "forecast": forecast,
        "resultInfo": {
            "availableMonths": len(all_months),
            "returnedMonths": len(months),
            "matchingLedgerEntries": ledger_total,
            "returnedLedgerEntries": len(ledger),
            "availableForecastEntries": len(all_forecast),
            "returnedForecastEntries": len(forecast),
        },
    }


def _limit_snapshot_state(
    state: dict[str, Any],
    *,
    snapshot_date: str | None,
    start_date: str | None,
    end_date: str | None,
    snapshot_limit: int,
    items_per_snapshot: int,
) -> dict[str, Any]:
    exact = _iso_date(snapshot_date, "snapshot_date")
    start = _iso_date(start_date, "start_date")
    end = _iso_date(end_date, "end_date")
    if start and end and start > end:
        raise ToolError("start_date must not be after end_date")

    all_snapshots = state.get("snapshots", [])
    snapshots = all_snapshots
    if exact:
        snapshots = [item for item in snapshots if item.get("date") == exact]
    if start:
        snapshots = [item for item in snapshots if str(item.get("date", "")) >= start]
    if end:
        snapshots = [item for item in snapshots if str(item.get("date", "")) <= end]
    matching_count = len(snapshots)
    snapshots = snapshots[:snapshot_limit]
    returned = []
    for snapshot in snapshots:
        item = dict(snapshot)
        all_items = snapshot.get("items", [])
        item["items"] = all_items[:items_per_snapshot]
        item["resultInfo"] = {
            "availableItems": len(all_items),
            "returnedItems": len(item["items"]),
        }
        returned.append(item)
    return {
        "snapshots": returned,
        "resultInfo": {
            "availableSnapshots": len(all_snapshots),
            "matchingSnapshots": matching_count,
            "returnedSnapshots": len(returned),
        },
    }


def _page(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    total = len(items)
    returned = items[:limit]
    return {
        "count": total,
        "returned": len(returned),
        "truncated": total > len(returned),
        "items": returned,
    }


def _is_completed_status(value: Any) -> bool:
    status = str(value or "").strip().lower()
    return status in {"done", "closed", "resolved", "complete", "completed"}


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
async def list_todo_lists(
    query: str | None = Field(default=None, description="Case-insensitive list-name search"),
    limit: int = Field(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List TriggerToDo task lists. Use this before filtering tasks by list ID."""
    data = await asyncio.to_thread(_read_todo_lists)
    items = data["items"]
    if query:
        needle = query.casefold()
        items = [item for item in items if needle in str(item.get("displayName", "")).casefold()]
    return _page(items, limit)


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
    include_details: bool = Field(default=False, description="Include body and recurrence details when true"),
    body_max_chars: int = Field(default=1000, ge=100, le=2000, description="Per-task body limit in detail mode"),
    limit: int = Field(default=50, ge=1, le=100),
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
    returned = []
    for source in items[:limit]:
        item = dict(source)
        if include_details:
            body = str(item.get("bodyContent") or "")
            item["bodyContent"] = body[:body_max_chars]
            item["bodyTruncated"] = len(body) > body_max_chars
        else:
            item.pop("bodyContent", None)
            item.pop("recurrenceJson", None)
        returned.append(item)
    return {"count": total, "returned": len(returned), "truncated": total > len(returned), "items": returned}


@mcp.tool(annotations=read_only)
async def list_trigger_rules(
    enabled_only: bool = Field(default=True, description="Return only enabled rules by default"),
    limit: int = Field(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List TriggerToDo automation rules; this never runs a trigger."""
    data = await _get_json(TRIGGER_URL, "/api/triggers")
    items = data.get("items", [])
    if enabled_only:
        items = [item for item in items if item.get("enabled") is True]
    return _page(items, limit)


@mcp.tool(annotations=read_only)
async def list_trigger_events(
    active_only: bool = Field(default=False, description="Return only active/occurred events when true"),
    limit: int = Field(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List TriggerToDo events and whether they have occurred."""
    data = await _get_json(TRIGGER_URL, "/api/events")
    items = data.get("items", [])
    if active_only:
        items = [item for item in items if item.get("is_active") is True]
    return _page(items, limit)


@mcp.tool(annotations=read_only)
async def list_epics(
    include_completed: bool = Field(default=False, description="Include completed/closed epics when true"),
    limit: int = Field(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List TriggerToDo epics with status and priority."""
    data = await _get_json(TRIGGER_URL, "/api/epics")
    items = data.get("items", [])
    if not include_completed:
        items = [item for item in items if not _is_completed_status(item.get("status"))]
    return _page(items, limit)


@mcp.tool(annotations=read_only)
async def list_milestones(
    start_date: str | None = Field(default=None, description="Inclusive milestone start date, YYYY-MM-DD"),
    end_date: str | None = Field(default=None, description="Inclusive milestone end date, YYYY-MM-DD"),
    include_links: bool = Field(default=False, description="Include linked Epic/task/Scrum details when true"),
    links_per_milestone: int = Field(default=50, ge=1, le=100, description="Maximum linked records of each type"),
    limit: int = Field(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List bounded TriggerToDo milestone summaries; linked records are opt-in."""
    start = _iso_date(start_date, "start_date")
    end = _iso_date(end_date, "end_date")
    if start and end and start > end:
        raise ToolError("start_date must not be after end_date")
    data = await _get_json(TRIGGER_URL, "/api/milestones")
    items = data.get("items", [])
    if start:
        items = [
            item
            for item in items
            if str(item.get("milestone_at") or "")[:10]
            and str(item.get("milestone_at") or "")[:10] >= start
        ]
    if end:
        items = [
            item
            for item in items
            if str(item.get("milestone_at") or "")[:10]
            and str(item.get("milestone_at") or "")[:10] <= end
        ]
    compact = []
    for source in items:
        item = dict(source)
        if include_links:
            for field in ("epic_keys", "task_ids", "scrum_ids", "epics", "tasks", "scrums"):
                item[field] = item.get(field, [])[:links_per_milestone]
            item["linkResultInfo"] = {
                "limitPerType": links_per_milestone,
                "truncated": any(
                    int(item.get("summary", {}).get(field, 0)) > links_per_milestone
                    for field in ("epics", "tasks", "scrums")
                ),
            }
        else:
            for field in ("epic_keys", "task_ids", "scrum_ids", "epics", "tasks", "scrums"):
                item.pop(field, None)
        compact.append(item)
    return _page(compact, limit)


@mcp.tool(annotations=read_only)
async def list_scrums(
    status: Literal["active", "draft", "completed", "all"] = "active",
    scrum_id: int | None = Field(default=None, ge=1, description="Return one Scrum by ID regardless of status"),
    include_tasks: bool = Field(default=False, description="Include task items; requires scrum_id"),
    limit: int = Field(default=5, ge=1, le=50),
    task_limit: int = Field(default=100, ge=1, le=200, description="Maximum task items for a specific Scrum"),
) -> dict[str, Any]:
    """List bounded Scrum summaries; defaults to active, and tasks require a specific Scrum ID."""
    if include_tasks and scrum_id is None:
        raise ToolError("include_tasks requires scrum_id")
    if scrum_id is None and status == "active":
        data = await _get_json(TRIGGER_URL, "/api/scrums/active")
        items = [data["item"]] if data.get("item") else []
    else:
        data = await _get_json(TRIGGER_URL, "/api/scrums")
        items = data.get("items", [])
        if scrum_id is not None:
            items = [item for item in items if item.get("id") == scrum_id]
        elif status != "all":
            items = [item for item in items if item.get("status") == status]

    compact = []
    for source in items:
        item = dict(source)
        tasks = item.get("items", [])
        if include_tasks:
            item["items"] = tasks[:task_limit]
            item["taskResultInfo"] = {
                "availableTasks": len(tasks),
                "returnedTasks": len(item["items"]),
                "truncated": len(tasks) > len(item["items"]),
            }
        else:
            item.pop("items", None)
        compact.append(item)
    return _page(compact, 1 if scrum_id is not None else limit)


@mcp.tool(annotations=read_only)
async def list_routine_checks(
    start_date: str = Field(description="Inclusive ISO date (YYYY-MM-DD)"),
    end_date: str = Field(description="Inclusive ISO date (YYYY-MM-DD)"),
    limit: int = Field(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """List TriggerToDo routine completion checks in a date range."""
    data = await _get_json(
        TRIGGER_URL, "/api/routines/checks", {"start_date": start_date, "end_date": end_date}
    )
    return _page(data.get("items", []), limit)


@mcp.tool(annotations=read_only)
async def get_finance_overview(
    month: str | None = Field(default=None, description="Exact report month in YYYY-MM; defaults to latest"),
    months_limit: int = Field(default=1, ge=1, le=12, description="Maximum report months to return"),
    ledger_start_date: str | None = Field(default=None, description="Inclusive ledger start date, YYYY-MM-DD"),
    ledger_end_date: str | None = Field(default=None, description="Inclusive ledger end date, YYYY-MM-DD"),
    ledger_limit: int = Field(default=100, ge=1, le=500, description="Maximum matching ledger entries"),
    include_forecast: bool = Field(default=False, description="Include forecast entries when true"),
    forecast_limit: int = Field(default=25, ge=1, le=100, description="Maximum forecast entries"),
) -> dict[str, Any]:
    """Read a bounded Fire finance view; defaults to the latest month and at most 100 ledger entries."""
    state = await asyncio.to_thread(_load_fire_state, "load_finance_state")
    return _limit_finance_state(
        state,
        month=month,
        months_limit=months_limit,
        ledger_start_date=ledger_start_date,
        ledger_end_date=ledger_end_date,
        ledger_limit=ledger_limit,
        include_forecast=include_forecast,
        forecast_limit=forecast_limit,
    )


@mcp.tool(annotations=read_only)
async def get_investments(
    snapshot_date: str | None = Field(default=None, description="Exact snapshot date, YYYY-MM-DD"),
    start_date: str | None = Field(default=None, description="Inclusive snapshot start date, YYYY-MM-DD"),
    end_date: str | None = Field(default=None, description="Inclusive snapshot end date, YYYY-MM-DD"),
    snapshot_limit: int = Field(default=1, ge=1, le=12, description="Maximum snapshots; defaults to latest only"),
    items_per_snapshot: int = Field(default=100, ge=1, le=200, description="Maximum holdings per snapshot"),
) -> dict[str, Any]:
    """Read bounded Fire investment snapshots; defaults to the latest snapshot only."""
    state = await asyncio.to_thread(_load_fire_state, "load_investment_state")
    return _limit_snapshot_state(
        state,
        snapshot_date=snapshot_date,
        start_date=start_date,
        end_date=end_date,
        snapshot_limit=snapshot_limit,
        items_per_snapshot=items_per_snapshot,
    )


@mcp.tool(annotations=read_only)
async def get_portfolio(
    snapshot_date: str | None = Field(default=None, description="Exact snapshot date, YYYY-MM-DD"),
    start_date: str | None = Field(default=None, description="Inclusive snapshot start date, YYYY-MM-DD"),
    end_date: str | None = Field(default=None, description="Inclusive snapshot end date, YYYY-MM-DD"),
    snapshot_limit: int = Field(default=1, ge=1, le=12, description="Maximum snapshots; defaults to latest only"),
    items_per_snapshot: int = Field(default=100, ge=1, le=200, description="Maximum holdings per snapshot"),
) -> dict[str, Any]:
    """Read bounded Fire portfolio snapshots; defaults to the latest snapshot only."""
    state = await asyncio.to_thread(_load_fire_state, "load_portfolio_state")
    return _limit_snapshot_state(
        state,
        snapshot_date=snapshot_date,
        start_date=start_date,
        end_date=end_date,
        snapshot_limit=snapshot_limit,
        items_per_snapshot=items_per_snapshot,
    )


app = mcp.streamable_http_app()
