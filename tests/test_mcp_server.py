from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from mcp.server.fastmcp.exceptions import ToolError


def _load_mcp_app(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_DATABASE", str(tmp_path / "mcp-auth.sqlite3"))
    monkeypatch.setenv("MCP_AUTH_USERNAME", "test-user")
    monkeypatch.setenv("MCP_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://watch0.top")
    monkeypatch.setenv(
        "CONCLUSION_DATABASE_PATH",
        str(tmp_path / "conclusion.sqlite3"),
    )
    sys.modules.pop("app.mcp_server", None)
    sys.modules.pop("app.mcp_auth", None)
    return importlib.import_module("app.mcp_server")


def test_mcp_requires_oauth_and_advertises_tool_side_effects(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    with TestClient(module.app, base_url="https://watch0.top") as client:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == "https://watch0.top/mcp"
        assert metadata.json()["scopes_supported"] == [
            "fengdock:read",
            "fengdock:write",
        ]

        unauthorized = client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert unauthorized.status_code == 401
        assert "resource_metadata=" in unauthorized.headers["www-authenticate"]

    tools = module.mcp._tool_manager.list_tools()
    assert tools
    by_name = {tool.name: tool for tool in tools}
    write_names = {
        "create_conclusion",
        "update_conclusion",
        "create_decision_model",
        "update_decision_model",
    }
    assert {name for name, tool in by_name.items() if not tool.annotations.readOnlyHint} == write_names
    assert all(
        tool.annotations and tool.annotations.readOnlyHint is True
        for name, tool in by_name.items()
        if name not in write_names
    )
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
                "scope": "fengdock:read fengdock:write",
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
                "scope": "fengdock:read fengdock:write",
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
        assert payload["scope"] == "fengdock:read fengdock:write"

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
        assert len(tools) == 20
        assert {tool["name"] for tool in tools} >= {
            "search_todos",
            "get_finance_overview",
            "search_conclusions",
            "create_conclusion",
            "update_conclusion",
            "list_decision_models",
            "update_decision_model",
        }
        schemas = {tool["name"]: tool["inputSchema"]["properties"] for tool in tools}
        assert schemas["list_scrums"]["status"]["default"] == "active"
        assert schemas["list_scrums"]["include_tasks"]["default"] is False
        assert schemas["list_scrums"]["limit"]["default"] == 5
        assert schemas["search_todos"]["include_details"]["default"] is False
        assert schemas["get_finance_overview"]["months_limit"]["default"] == 1
        assert schemas["get_investments"]["snapshot_limit"]["default"] == 1
        assert schemas["list_conclusions"]["limit"]["default"] == 50


def test_conclusion_writes_require_write_scope(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "get_access_token",
        lambda: SimpleNamespace(scopes=["fengdock:read"]),
    )

    def attempt_write():
        with pytest.raises(ToolError, match="fengdock:write"):
            asyncio.run(
                module.create_conclusion(
                    title="Blocked write",
                    question="Should this be written?",
                    conclusion="No.",
                    reason="The token is read-only.",
                    category="Test",
                    confidence="High",
                )
            )

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(attempt_write).result()


def test_conclusion_mcp_tools_support_search_analysis_and_safe_writes(tmp_path, monkeypatch):
    module = _load_mcp_app(tmp_path, monkeypatch)

    async def scenario():
        created = await module.create_conclusion(
            title="Keep an emergency fund",
            question="Should emergency cash be invested?",
            conclusion="Keep six months of expenses liquid.",
            reason="Availability matters more than maximizing return.",
            category="Finance",
            confidence="High",
            tags=["Emergency Fund", "Safety"],
        )
        assert created["id"] == 1
        assert created["decisionAnalysis"] == {"version": 1, "models": []}

        listed = await module.list_conclusions(limit=10)
        assert listed["count"] == 1
        searched = await module.search_conclusions(
            query="liquid",
            category="finance",
            tag="emergency fund",
            limit=10,
        )
        assert searched["items"] == [created]
        assert await module.get_conclusion(conclusion_id=1) == created

        models = await module.list_decision_models()
        assert models["count"] == 7
        assert list(models["models"]) == [
            "precedent-review",
            "munger-checklist",
            "scenario-range",
            "time-horizons",
            "inversion",
            "inaction-value",
            "reversibility",
        ]
        assert set(models["models"]["time-horizons"]) == {"name", "explanation"}
        assert models["versions"]["time-horizons"] == 1
        assert "every model" in models["usage"]
        reversibility = await module.get_decision_model(model_id="reversibility")
        assert reversibility == {
            "modelId": "reversibility",
            "version": 1,
            "model": {
                "name": "可逆性判断",
                "explanation": models["models"]["reversibility"]["explanation"],
            },
        }

        updated = await module.update_conclusion(
            conclusion_id=1,
            expected_updated_at=created["updatedAt"],
            conclusion="Keep six months of expenses liquid and separate.",
        )
        assert updated["conclusion"].endswith("and separate.")

        custom = await module.create_decision_model(
            model_id="constraint-check",
            name="约束检查",
            explanation="检查必须满足的硬约束，并找出最先限制结果的瓶颈。",
        )
        assert custom == {
            "modelId": "constraint-check",
            "version": 1,
            "model": {
                "name": "约束检查",
                "explanation": "检查必须满足的硬约束，并找出最先限制结果的瓶颈。",
            },
        }
        updated_model = await module.update_decision_model(
            model_id="constraint-check",
            expected_version=1,
            name="关键约束检查",
            explanation="确认硬约束，并找出真正限制结果的瓶颈。",
        )
        assert updated_model == {
            "modelId": "constraint-check",
            "version": 2,
            "model": {
                "name": "关键约束检查",
                "explanation": "确认硬约束，并找出真正限制结果的瓶颈。",
            },
        }
        with pytest.raises(ToolError, match="currentVersion=2"):
            await module.update_decision_model(
                model_id="constraint-check",
                expected_version=1,
                name="过期修改",
                explanation="这次更新应该失败。",
            )

        with pytest.raises(ToolError, match="currentUpdatedAt"):
            await module.update_conclusion(
                conclusion_id=1,
                expected_updated_at=created["updatedAt"],
                conclusion="Overwrite a newer decision.",
            )

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, scenario()).result()


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
