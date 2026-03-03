"""
FastAPI reverse proxy for Anthropic with full interaction logging to JSONL.

ENV:
  ANTHROPIC_API_KEY    - upstream key (optional if client supplies it)
  PROXY_PREFIX         - optional, serve under /<prefix>
  LOG_JSONL_PATH       - default: ./logs/interactions.jsonl
  LOG_SSE_RAW          - "1" to also store raw SSE lines (can be large)
  LOG_BODY_MAX_BYTES   - truncate stored request/response bodies (default: no trunc)
"""

import os
import json
import time
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware

# ---------- Config ----------
# Two upstream targets
# For ChatGPT login users, both should point to chatgpt.com/backend-api/codex
CODEX_RESPONSE_BASE_URL = os.getenv("CODEX_RESPONSE_BASE_URL", "https://chatgpt.com/backend-api/codex")
CODEX_LOGIN_BASE_URL = os.getenv("CODEX_LOGIN_BASE_URL", "https://chatgpt.com/backend-api")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PROXY_PREFIX = os.getenv("PROXY_PREFIX", "").strip("/")
TIMEOUT = httpx.Timeout(60.0, connect=10.0)

LOG_JSONL_PATH = os.getenv("LOG_JSONL_PATH", "./logs/codex_interactions.jsonl")
LOG_SSE_RAW = os.getenv("LOG_SSE_RAW", "0") == "1"
LOG_BODY_MAX_BYTES = int(os.getenv("LOG_BODY_MAX_BYTES", "0"))  # 0 = unlimited
LOG_JSONL_MAX_BYTES = int(os.getenv("LOG_JSONL_MAX_BYTES", "0"))  # 0 = unlimited
LOG_RETENTION_SECONDS = int(os.getenv("LOG_RETENTION_SECONDS", "3600"))  # 0 = disabled

os.makedirs(os.path.dirname(LOG_JSONL_PATH) or ".", exist_ok=True)

app = FastAPI(root_path=f"/{PROXY_PREFIX}" if PROXY_PREFIX else "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = httpx.AsyncClient(timeout=TIMEOUT)
_log_write_lock = threading.Lock()

# ---------- Utilities ----------

SENSITIVE_HEADER_KEYS = {
    "authorization", "proxy-authorization", "x-api-key", "cookie", "set-cookie"
}

def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADER_KEYS:
            out[k] = "****"
        else:
            out[k] = v
    return out

def filter_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    hop_by_hop = {
        "content-length", "transfer-encoding", "connection", "keep-alive",
        "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade",
    }
    return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}

def maybe_json(b: bytes) -> Any:
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return None

def trunc(b: bytes) -> bytes:
    if LOG_BODY_MAX_BYTES and len(b) > LOG_BODY_MAX_BYTES:
        return b[:LOG_BODY_MAX_BYTES]
    return b

async def append_jsonl(entry: Dict[str, Any]) -> None:
    line = json.dumps(entry, ensure_ascii=False)
    # write in a thread to avoid blocking the event loop
    await asyncio.to_thread(
        _append_line_sync,
        LOG_JSONL_PATH,
        line,
        LOG_JSONL_MAX_BYTES,
        LOG_RETENTION_SECONDS,
    )

def _append_line_sync(path: str, line: str, max_bytes: int, retention_seconds: int) -> None:
    with _log_write_lock:
        if max_bytes:
            try:
                current_size = os.path.getsize(path)
            except FileNotFoundError:
                current_size = 0
            # If the next write would exceed the cap, truncate first.
            if current_size + len(line) + 1 > max_bytes:
                with open(path, "w", encoding="utf-8"):
                    pass
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
        _trim_jsonl_by_age_sync(path, retention_seconds)

def _trim_jsonl_by_age_sync(path: str, retention_seconds: int) -> None:
    if retention_seconds <= 0:
        return
    if not os.path.exists(path):
        return
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention_seconds)
    tmp_path = f"{path}.tmp"
    with open(path, "r", encoding="utf-8") as src, open(tmp_path, "w", encoding="utf-8") as dst:
        for raw in src:
            keep = True
            try:
                obj = json.loads(raw)
                ts = obj.get("t")
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    keep = dt >= cutoff
            except Exception:
                keep = True
            if keep:
                if raw.endswith("\n"):
                    dst.write(raw)
                else:
                    dst.write(raw + "\n")
    os.replace(tmp_path, path)

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------- Health ----------
@app.get("/_/healthz")
async def healthz():
    return PlainTextResponse("ok")

@app.get("/_/log_path")
async def log_path():
    return PlainTextResponse(LOG_JSONL_PATH)

@app.get("/hello")
async def hello():
    return PlainTextResponse("hell0")

# ---------- Helper to determine upstream URL ----------
def get_upstream_url(full_path: str) -> tuple[str, str]:
    """
    Returns (upstream_url, remaining_path) based on the route prefix.
    - /codex-response/* -> https://api.openai.com/v1/*
    - /codex-login/api/codex/* -> https://chatgpt.com/backend-api/codex/*
    """
    if full_path.startswith("codex-response/"):
        remaining = full_path[len("codex-response/"):]
        return f"{CODEX_RESPONSE_BASE_URL}/{remaining}", remaining
    elif full_path.startswith("codex-login/"):
        remaining = full_path[len("codex-login/"):]
        # Transform api/codex/* -> codex/* for chatgpt.com/backend-api
        if remaining.startswith("api/"):
            remaining = remaining[len("api/"):]
        return f"{CODEX_LOGIN_BASE_URL}/{remaining}", remaining
    elif full_path == "codex-response":
        return CODEX_RESPONSE_BASE_URL, ""
    elif full_path == "codex-login":
        return CODEX_LOGIN_BASE_URL, ""
    else:
        # Default fallback to codex-response URL
        return f"{CODEX_RESPONSE_BASE_URL}/{full_path}", full_path

# ---------- Core proxy ----------
@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(full_path: str, request: Request):
    t0 = time.perf_counter()
    target_url, remaining_path = get_upstream_url(full_path)

    # Forward & sanitize request headers
    fwd_headers = dict(request.headers)
    fwd_headers.pop("host", None)
    fwd_headers.pop("content-length", None)  # let httpx set it

    # For chatgpt.com routes, add browser-like headers to help with Cloudflare
    if full_path.startswith("codex-login") or full_path.startswith("codex-response"):
        fwd_headers["user-agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        fwd_headers["accept-language"] = "en-US,en;q=0.9"
        fwd_headers["origin"] = "https://chatgpt.com"
        fwd_headers["referer"] = "https://chatgpt.com/"
        fwd_headers["sec-ch-ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        fwd_headers["sec-ch-ua-mobile"] = "?0"
        fwd_headers["sec-ch-ua-platform"] = '"Windows"'
        fwd_headers["sec-fetch-dest"] = "empty"
        fwd_headers["sec-fetch-mode"] = "cors"
        fwd_headers["sec-fetch-site"] = "same-origin"

    if ANTHROPIC_API_KEY:
        # Upstream key takes precedence
        fwd_headers["x-api-key"] = ANTHROPIC_API_KEY

    # Body & query
    req_body_bytes = await request.body()
    req_params = dict(request.query_params)
    req_json = maybe_json(req_body_bytes)

    # Build & send upstream request with streaming enabled
    req_up = client.build_request(
        method=request.method,
        url=target_url,
        headers=fwd_headers,
        params=req_params,
        content=req_body_bytes,
    )

    try:
        upstream = await client.send(req_up, stream=True)
    except Exception as e:
        # Log failure to contact upstream
        entry = {
            "t": utc_now_iso(),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": f"upstream_request_failed: {type(e).__name__}: {e}",
            "req": {
                "method": request.method,
                "url": str(request.url),
                "path": f"/{full_path}",
                "query": req_params,
                "client": getattr(request.client, "host", None),
                "headers": sanitize_headers(dict(request.headers)),
                "body_json": req_json if req_json is not None else None,
                "body_text": None if req_json is not None else trunc(req_body_bytes).decode("utf-8", "replace"),
            },
        }
        await append_jsonl(entry)
        return PlainTextResponse("Upstream request failed", status_code=502)

    content_type = upstream.headers.get("content-type", "")
    resp_headers = filter_response_headers(dict(upstream.headers))

    # ---------- SSE path (streaming) ----------
    if content_type.startswith("text/event-stream"):
        # Buffers for logging
        sse_raw_lines: List[str] = [] if LOG_SSE_RAW else None
        sse_events: List[Dict[str, Any]] = []
        aggregated_text: List[str] = []
        last_message_delta: Optional[Dict[str, Any]] = None

        async def event_stream():
            nonlocal sse_raw_lines, sse_events, aggregated_text, last_message_delta, upstream
            try:
                async for line in upstream.aiter_lines():
                    # Forward to client ASAP
                    yield (line + "\n").encode("utf-8")

                    # Logging buffers
                    if LOG_SSE_RAW and sse_raw_lines is not None:
                        sse_raw_lines.append(line)

                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if not payload:  # keep-alives possible
                            continue
                        try:
                            obj = json.loads(payload)
                            sse_events.append(obj)

                            # Accumulate text tokens if present (Anthropic "content_block_delta")
                            t = obj.get("type")
                            if t == "content_block_delta":
                                delta = obj.get("delta", {})
                                txt = delta.get("text")
                                if isinstance(txt, str):
                                    aggregated_text.append(txt)
                            elif t == "message_delta":
                                last_message_delta = obj
                        except Exception:
                            # Ignore unparseable data payloads
                            pass
            finally:
                await upstream.aclose()
                # After stream completes, write JSONL
                entry = {
                    "t": utc_now_iso(),
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "req": {
                        "method": request.method,
                        "url": str(request.url),
                        "path": f"/{full_path}",
                        "query": req_params,
                        "client": getattr(request.client, "host", None),
                        "headers": sanitize_headers(dict(request.headers)),
                        "body_json": req_json if req_json is not None else None,
                        "body_text": None if req_json is not None else trunc(req_body_bytes).decode("utf-8", "replace"),
                    },
                    "resp": {
                        "status": upstream.status_code,
                        "headers": sanitize_headers(resp_headers),
                        "sse_events_count": len(sse_events),
                        "sse_text": "".join(aggregated_text) if aggregated_text else None,
                        "final_message_meta": last_message_delta,
                        "raw_sse": "\n".join(sse_raw_lines) if LOG_SSE_RAW and sse_raw_lines is not None else None,
                    },
                }
                await append_jsonl(entry)

        return StreamingResponse(
            event_stream(),
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    # ---------- Non-SSE path (buffered) ----------
    content_bytes = await upstream.aread()
    await upstream.aclose()

    resp_json = maybe_json(content_bytes)
    entry = {
        "t": utc_now_iso(),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "req": {
            "method": request.method,
            "url": str(request.url),
            "path": f"/{full_path}",
            "query": req_params,
            "client": getattr(request.client, "host", None),
            "headers": sanitize_headers(dict(request.headers)),
            "body_json": req_json if req_json is not None else None,
            "body_text": None if req_json is not None else trunc(req_body_bytes).decode("utf-8", "replace"),
        },
        "resp": {
            "status": upstream.status_code,
            "headers": sanitize_headers(resp_headers),
            "body_json": resp_json if resp_json is not None else None,
            "body_text": None if resp_json is not None else trunc(content_bytes).decode("utf-8", "replace"),
        },
    }
    await append_jsonl(entry)

    return Response(
        content=content_bytes,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )
