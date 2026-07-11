from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import sys
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from mcp.server.fastmcp.exceptions import ToolError


def _load_mcp_app(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_DATABASE", str(tmp_path / "mcp-auth.sqlite3"))
    monkeypatch.setenv("MCP_AUTH_USERNAME", "test-user")
    monkeypatch.setenv("MCP_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://watch0.top")
    sys.modules.pop("app.mcp_server", None)
    sys.modules.pop("app.mcp_auth", None)
    return importlib.import_module("app.mcp_server")


def test_mcp_requires_oauth_and_advertises_read_only_tools(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    with TestClient(module.app, base_url="https://watch0.top") as client:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == "https://watch0.top/mcp"

        unauthorized = client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert unauthorized.status_code == 401
        assert "resource_metadata=" in unauthorized.headers["www-authenticate"]

    tools = module.mcp._tool_manager.list_tools()
    assert tools
    assert all(tool.annotations and tool.annotations.readOnlyHint is True for tool in tools)
    assert all(tool.annotations and tool.annotations.destructiveHint is False for tool in tools)


def test_oauth_pkce_flow_issues_access_and_refresh_tokens(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect_uri = "https://chatgpt.com/aip/oauth/callback"

    with TestClient(module.app, base_url="https://watch0.top", follow_redirects=False) as client:
        registration = client.post(
            "/register",
            json={
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "fengdock:read",
                "client_name": "ChatGPT test",
            },
        )
        assert registration.status_code == 201
        client_id = registration.json()["client_id"]

        authorization = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "fengdock:read",
                "state": "client-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://watch0.top/mcp",
            },
        )
        assert authorization.status_code == 302
        nonce = parse_qs(urlparse(authorization.headers["location"]).query)["nonce"][0]

        login_page = client.get(f"/login?nonce={nonce}")
        assert login_page.status_code == 200
        assert 'name="password"' in login_page.text
        assert 'name="username"' not in login_page.text
        assert "form-action 'self' https://chatgpt.com" in login_page.headers["content-security-policy"]

        login = client.post(
            "/login/callback",
            data={"nonce": nonce, "password": "test-password"},
        )
        assert login.status_code == 302
        callback = urlparse(login.headers["location"])
        callback_query = parse_qs(callback.query)
        assert callback_query["state"] == ["client-state"]

        token = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": callback_query["code"][0],
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
                "resource": "https://watch0.top/mcp",
            },
        )
        assert token.status_code == 200, token.text
        payload = token.json()
        assert payload["token_type"] == "Bearer"
        assert payload["access_token"]
        assert payload["refresh_token"]
        assert payload["scope"] == "fengdock:read"

        authorized = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {payload['access_token']}",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert authorized.status_code == 200, authorized.text
        assert authorized.json()["result"]["serverInfo"]["name"] == "FengDock"

        listed = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {payload['access_token']}",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        tools = listed.json()["result"]["tools"]
        assert len(tools) == 11
        assert {tool["name"] for tool in tools} >= {"search_todos", "get_finance_overview"}
        schemas = {tool["name"]: tool["inputSchema"]["properties"] for tool in tools}
        assert schemas["list_scrums"]["status"]["default"] == "active"
        assert schemas["list_scrums"]["include_tasks"]["default"] is False
        assert schemas["list_scrums"]["limit"]["default"] == 5
        assert schemas["search_todos"]["include_details"]["default"] is False
        assert schemas["get_finance_overview"]["months_limit"]["default"] == 1
        assert schemas["get_investments"]["snapshot_limit"]["default"] == 1


def test_finance_results_default_to_latest_month_and_bounded_entries(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    state = {
        "months": [{"label": "2026-07"}, {"label": "2026-06"}],
        "ledger": [
            {"date": "2026-07-03", "amount": -3},
            {"date": "2026-07-02", "amount": -2},
            {"date": "2026-06-01", "amount": -1},
        ],
        "forecast": [{"year": 2027}, {"year": 2028}],
    }
    result = module._limit_finance_state(
        state,
        month=None,
        months_limit=1,
        ledger_start_date=None,
        ledger_end_date=None,
        ledger_limit=1,
        include_forecast=False,
        forecast_limit=25,
    )
    assert result["months"] == [{"label": "2026-07"}]
    assert result["ledger"] == [{"date": "2026-07-03", "amount": -3}]
    assert result["forecast"] == []
    assert result["resultInfo"]["matchingLedgerEntries"] == 2


def test_snapshot_results_support_dates_and_limits(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    state = {
        "snapshots": [
            {"date": "2026-07-03", "items": [{"id": "a"}, {"id": "b"}]},
            {"date": "2026-06-01", "items": [{"id": "c"}]},
        ]
    }
    result = module._limit_snapshot_state(
        state,
        snapshot_date=None,
        start_date="2026-07-01",
        end_date=None,
        snapshot_limit=1,
        items_per_snapshot=1,
    )
    assert result["resultInfo"] == {
        "availableSnapshots": 2,
        "matchingSnapshots": 1,
        "returnedSnapshots": 1,
    }
    assert result["snapshots"][0]["items"] == [{"id": "a"}]
    assert result["snapshots"][0]["resultInfo"] == {"availableItems": 2, "returnedItems": 1}


def test_trigger_tools_default_to_bounded_summaries(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "_read_todo_lists",
        lambda: {
            "count": 2,
            "items": [
                {"id": "list-1", "displayName": "Work"},
                {"id": "list-2", "displayName": "Home"},
            ],
        },
    )
    responses = {
        "/api/todo/cache/tasks": {
            "items": [
                {
                    "listId": "list-1",
                    "taskId": "task-1",
                    "title": "Ship MCP",
                    "bodyContent": "private details",
                    "recurrenceJson": "{}",
                    "status": "notStarted",
                }
            ]
        },
        "/api/triggers": {"items": [{"id": 1, "enabled": True}, {"id": 2, "enabled": False}]},
        "/api/events": {"items": [{"id": 1, "is_active": True}, {"id": 2, "is_active": False}]},
        "/api/epics": {"items": [{"id": 1, "status": "active"}, {"id": 2, "status": "completed"}]},
        "/api/milestones": {
            "items": [
                {
                    "id": 1,
                    "milestone_at": "2026-07-20",
                    "summary": {"epics": 1, "tasks": 1, "scrums": 1},
                    "epic_keys": ["EPIC-1"],
                    "task_ids": ["task-1"],
                    "scrum_ids": ["1"],
                    "epics": [{"epic_key": "EPIC-1"}],
                    "tasks": [{"task_id": "task-1"}],
                    "scrums": [{"id": 1}],
                }
            ]
        },
        "/api/scrums/active": {
            "item": {
                "id": 1,
                "status": "active",
                "summary": {"items": 2},
                "items": [{"id": 1}, {"id": 2}],
            }
        },
        "/api/scrums": {
            "items": [
                {
                    "id": 1,
                    "status": "active",
                    "summary": {"items": 2},
                    "items": [{"id": 1}, {"id": 2}],
                }
            ]
        },
        "/api/routines/checks": {"items": [{"id": 1}, {"id": 2}]},
    }

    async def fake_get_json(_base_url, path, params=None):
        return responses[path]

    monkeypatch.setattr(module, "_get_json", fake_get_json)

    async def scenario():
        lists = await module.list_todo_lists(query="work", limit=10)
        assert lists["items"] == [{"id": "list-1", "displayName": "Work"}]

        tasks = await module.search_todos(
            query=None,
            pool=None,
            workflow_status=None,
            task_status=None,
            list_id=None,
            include_details=False,
            body_max_chars=1000,
            limit=50,
        )
        assert "bodyContent" not in tasks["items"][0]
        assert "recurrenceJson" not in tasks["items"][0]

        rules = await module.list_trigger_rules(enabled_only=True, limit=50)
        assert [item["id"] for item in rules["items"]] == [1]
        events = await module.list_trigger_events(active_only=True, limit=50)
        assert [item["id"] for item in events["items"]] == [1]
        epics = await module.list_epics(include_completed=False, limit=50)
        assert [item["id"] for item in epics["items"]] == [1]

        milestones = await module.list_milestones(
            start_date="2026-07-01",
            end_date="2026-07-31",
            include_links=False,
            links_per_milestone=50,
            limit=20,
        )
        assert milestones["items"][0]["summary"] == {"epics": 1, "tasks": 1, "scrums": 1}
        assert "tasks" not in milestones["items"][0]

        scrums = await module.list_scrums(
            status="active", scrum_id=None, include_tasks=False, limit=5, task_limit=100
        )
        assert scrums["returned"] == 1
        assert "items" not in scrums["items"][0]
        detail = await module.list_scrums(
            status="all", scrum_id=1, include_tasks=True, limit=5, task_limit=1
        )
        assert detail["items"][0]["items"] == [{"id": 1}]
        assert detail["items"][0]["taskResultInfo"]["truncated"] is True
        with pytest.raises(ToolError, match="requires scrum_id"):
            await module.list_scrums(
                status="all", scrum_id=None, include_tasks=True, limit=5, task_limit=100
            )

        routines = await module.list_routine_checks(
            start_date="2026-07-01", end_date="2026-07-31", limit=1
        )
        assert routines["returned"] == 1
        assert routines["truncated"] is True

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, scenario()).result()
