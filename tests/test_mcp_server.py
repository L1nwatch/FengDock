from __future__ import annotations

import base64
import hashlib
import importlib
import sys
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient


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
