"""Persistent single-user OAuth provider for the FengDock MCP server."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


ACCESS_TOKEN_SECONDS = 60 * 60
REFRESH_TOKEN_SECONDS = 30 * 24 * 60 * 60
AUTH_STATE_SECONDS = 10 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PersistentOAuthProvider:
    """OAuth 2.1 provider with PKCE, DCR, refresh rotation, and SQLite storage."""

    def __init__(self) -> None:
        self.public_url = os.getenv("MCP_PUBLIC_URL", "https://watch0.top").rstrip("/")
        self.resource_url = f"{self.public_url}/mcp"
        self.username = os.getenv("MCP_AUTH_USERNAME", "watch")
        self.password = os.getenv("MCP_AUTH_PASSWORD", "")
        self.scope = "fengdock:read"
        self.db_path = Path(os.getenv("MCP_AUTH_DATABASE", "/app/data/mcp-auth.sqlite3"))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    nonce TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_codes (
                    code_hash TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
                    token_hash TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_login_attempts (
                    remote_key TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL,
                    window_started INTEGER NOT NULL
                );
                """
            )

    def _cleanup(self, conn: sqlite3.Connection) -> None:
        now = int(time.time())
        for table in ("oauth_states", "oauth_codes", "oauth_access_tokens", "oauth_refresh_tokens"):
            conn.execute(f"DELETE FROM {table} WHERE expires_at < ?", (now,))

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row["payload"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("OAuth client_id is required")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO oauth_clients(client_id, payload) VALUES (?, ?)",
                (client_info.client_id, client_info.model_dump_json()),
            )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not client.client_id:
            raise AuthorizeError("invalid_request", "Invalid OAuth client")
        if params.resource and params.resource.rstrip("/") != self.resource_url:
            raise AuthorizeError("invalid_request", "The requested resource is not this MCP server")
        nonce = secrets.token_urlsafe(32)
        payload = {
            "client_id": client.client_id,
            "client_state": params.state,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "resource": params.resource or self.resource_url,
            "scopes": params.scopes or [self.scope],
        }
        with self._connect() as conn:
            self._cleanup(conn)
            conn.execute(
                "INSERT INTO oauth_states(nonce, payload, expires_at) VALUES (?, ?, ?)",
                (nonce, json.dumps(payload), int(time.time()) + AUTH_STATE_SECONDS),
            )
        return f"{self.public_url}/login?nonce={nonce}"

    async def get_login_page(self, nonce: str) -> HTMLResponse:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM oauth_states WHERE nonce = ? AND expires_at >= ?",
                (nonce, int(time.time())),
            ).fetchone()
        if not row:
            raise HTTPException(400, "Authorization request expired or invalid")
        disabled = " disabled" if not self.password else ""
        message = (
            "Enter the FengDock MCP credentials."
            if self.password
            else "MCP_AUTH_PASSWORD is not configured on the server."
        )
        content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Authorize FengDock</title>
<style>body{{font:16px system-ui;max-width:420px;margin:10vh auto;padding:24px;color:#18202b}}
label{{display:block;margin:18px 0 6px}}input{{box-sizing:border-box;width:100%;padding:11px;border:1px solid #bbc3ce;border-radius:8px}}
button{{margin-top:22px;padding:11px 18px;border:0;border-radius:8px;background:#1668dc;color:white;font-weight:600}}</style>
</head><body><h1>Authorize FengDock</h1><p>{html.escape(message)}</p>
<form action="/login/callback" method="post">
<input type="hidden" name="nonce" value="{html.escape(nonce, quote=True)}">
<label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit"{disabled}>Authorize read-only access</button></form></body></html>"""
        return HTMLResponse(
            content,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def _remote_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        return forwarded or (request.client.host if request.client else "unknown")

    def _login_allowed(self, conn: sqlite3.Connection, remote_key: str) -> bool:
        row = conn.execute(
            "SELECT failures, window_started FROM oauth_login_attempts WHERE remote_key = ?", (remote_key,)
        ).fetchone()
        if not row:
            return True
        if int(row["window_started"]) + LOGIN_WINDOW_SECONDS < int(time.time()):
            conn.execute("DELETE FROM oauth_login_attempts WHERE remote_key = ?", (remote_key,))
            return True
        return int(row["failures"]) < LOGIN_MAX_FAILURES

    def _record_login_failure(self, conn: sqlite3.Connection, remote_key: str) -> None:
        now = int(time.time())
        row = conn.execute(
            "SELECT failures, window_started FROM oauth_login_attempts WHERE remote_key = ?", (remote_key,)
        ).fetchone()
        if not row or int(row["window_started"]) + LOGIN_WINDOW_SECONDS < now:
            conn.execute(
                "INSERT OR REPLACE INTO oauth_login_attempts(remote_key, failures, window_started) VALUES (?, 1, ?)",
                (remote_key, now),
            )
        else:
            conn.execute(
                "UPDATE oauth_login_attempts SET failures = failures + 1 WHERE remote_key = ?", (remote_key,)
            )

    async def handle_login_callback(self, request: Request) -> Response:
        form = await request.form()
        password, nonce = form.get("password"), form.get("nonce")
        if not all(isinstance(value, str) for value in (password, nonce)):
            raise HTTPException(400, "Missing login fields")
        assert isinstance(password, str) and isinstance(nonce, str)
        remote_key = self._remote_key(request)
        with self._connect() as conn:
            self._cleanup(conn)
            if not self._login_allowed(conn, remote_key):
                raise HTTPException(429, "Too many login attempts; try again later")
            if not self.password or not hmac.compare_digest(password, self.password):
                self._record_login_failure(conn, remote_key)
                raise HTTPException(401, "Invalid credentials")
            row = conn.execute("SELECT payload FROM oauth_states WHERE nonce = ?", (nonce,)).fetchone()
            if not row:
                raise HTTPException(400, "Authorization request expired or invalid")
            state = json.loads(row["payload"])
            code = secrets.token_urlsafe(32)
            auth_code = AuthorizationCode(
                code=code,
                client_id=state["client_id"],
                redirect_uri=AnyHttpUrl(state["redirect_uri"]),
                redirect_uri_provided_explicitly=state["redirect_uri_provided_explicitly"],
                expires_at=time.time() + 5 * 60,
                scopes=state["scopes"],
                code_challenge=state["code_challenge"],
                resource=state["resource"],
                subject=self.username,
            )
            conn.execute("DELETE FROM oauth_states WHERE nonce = ?", (nonce,))
            conn.execute("DELETE FROM oauth_login_attempts WHERE remote_key = ?", (remote_key,))
            conn.execute(
                "INSERT INTO oauth_codes(code_hash, payload, expires_at) VALUES (?, ?, ?)",
                (_token_hash(code), auth_code.model_dump_json(), int(auth_code.expires_at)),
            )
        return RedirectResponse(
            construct_redirect_uri(
                state["redirect_uri"], code=code, state=state.get("client_state")
            ),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        with self._connect() as conn:
            self._cleanup(conn)
            row = conn.execute(
                "SELECT payload FROM oauth_codes WHERE code_hash = ?", (_token_hash(authorization_code),)
            ).fetchone()
        if not row:
            return None
        code = AuthorizationCode.model_validate_json(row["payload"])
        return code if code.client_id == client.client_id else None

    def _issue_tokens(self, client_id: str, scopes: list[str], subject: str | None, resource: str) -> OAuthToken:
        now = int(time.time())
        access_value = secrets.token_urlsafe(48)
        refresh_value = secrets.token_urlsafe(48)
        access = AccessToken(
            token=access_value,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + ACCESS_TOKEN_SECONDS,
            resource=resource,
            subject=subject,
        )
        refresh = RefreshToken(
            token=refresh_value,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + REFRESH_TOKEN_SECONDS,
            subject=subject,
        )
        refresh_payload = {"token": refresh.model_dump(mode="json"), "resource": resource}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO oauth_access_tokens(token_hash, payload, expires_at) VALUES (?, ?, ?)",
                (_token_hash(access_value), access.model_dump_json(), access.expires_at),
            )
            conn.execute(
                "INSERT INTO oauth_refresh_tokens(token_hash, payload, expires_at) VALUES (?, ?, ?)",
                (_token_hash(refresh_value), json.dumps(refresh_payload), refresh.expires_at),
            )
        return OAuthToken(
            access_token=access_value,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh_value,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM oauth_codes WHERE code_hash = ?", (_token_hash(authorization_code.code),)
            ).rowcount
        if not deleted or not client.client_id:
            raise ValueError("Invalid or already-used authorization code")
        return self._issue_tokens(
            client.client_id,
            authorization_code.scopes,
            authorization_code.subject,
            authorization_code.resource or self.resource_url,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        with self._connect() as conn:
            self._cleanup(conn)
            row = conn.execute(
                "SELECT payload FROM oauth_access_tokens WHERE token_hash = ?", (_token_hash(token),)
            ).fetchone()
        if not row:
            return None
        stored = AccessToken.model_validate_json(row["payload"])
        stored.token = token
        return stored if stored.resource == self.resource_url else None

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        with self._connect() as conn:
            self._cleanup(conn)
            row = conn.execute(
                "SELECT payload FROM oauth_refresh_tokens WHERE token_hash = ?", (_token_hash(refresh_token),)
            ).fetchone()
        if not row:
            return None
        stored = RefreshToken.model_validate(json.loads(row["payload"])["token"])
        stored.token = refresh_token
        return stored if stored.client_id == client.client_id else None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM oauth_refresh_tokens WHERE token_hash = ?", (_token_hash(refresh_token.token),)
            ).fetchone()
            deleted = conn.execute(
                "DELETE FROM oauth_refresh_tokens WHERE token_hash = ?", (_token_hash(refresh_token.token),)
            ).rowcount
        if not row or not deleted or not client.client_id:
            raise ValueError("Invalid or already-used refresh token")
        requested = scopes or refresh_token.scopes
        if not set(requested).issubset(set(refresh_token.scopes)):
            raise ValueError("Requested scopes exceed the original grant")
        resource = json.loads(row["payload"])["resource"]
        return self._issue_tokens(client.client_id, requested, refresh_token.subject, resource)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        digest = _token_hash(token.token)
        with self._connect() as conn:
            conn.execute("DELETE FROM oauth_access_tokens WHERE token_hash = ?", (digest,))
            conn.execute("DELETE FROM oauth_refresh_tokens WHERE token_hash = ?", (digest,))
