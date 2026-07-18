"""Execution of user-defined HTTP tools (docs/06 §5).

Config shape (Tool.config):
    {"method": "GET|POST|...", "url": "...", "headers": {..}, "body": {..}|str, "timeout": float?}

`{{arg}}` placeholders in the url / header values / body are filled from the model-supplied
arguments. SSRF-guarded; times out per settings.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.rag.loaders import _is_blocked_host
from app.tools.base import ToolResult

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _render(value: Any, args: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: str(args.get(m.group(1), "")), value)
    if isinstance(value, dict):
        return {k: _render(v, args) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, args) for v in value]
    return value


async def execute_http_tool(config: dict[str, Any], args: dict[str, Any]) -> ToolResult:
    url = _render(str(config.get("url", "")), args).strip()
    method = str(config.get("method", "GET")).upper()
    if not url:
        return ToolResult(output={}, status="error", error="tool has no url configured")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ToolResult(output={}, status="error", error="only http(s) URLs are allowed")
    if _is_blocked_host(parsed.hostname):
        return ToolResult(output={}, status="error", error="refusing to call a private/loopback host")

    headers = _render(config.get("headers") or {}, args)
    body = _render(config.get("body"), args) if config.get("body") is not None else None
    timeout = float(config.get("timeout", settings.tool_timeout_seconds))

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            kwargs: dict[str, Any] = {"headers": headers}
            if body is not None:
                if isinstance(body, str):
                    kwargs["content"] = body
                else:
                    kwargs["json"] = body
            resp = await client.request(method, url, **kwargs)
            text = resp.text[:4000]
    except httpx.HTTPError as exc:
        return ToolResult(output={}, status="error", error=f"request failed: {exc}")

    parsed_body: Any = text
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        try:
            parsed_body = resp.json()
        except ValueError:
            pass
    status = "success" if resp.status_code < 400 else "error"
    return ToolResult(
        output={"status_code": resp.status_code, "body": parsed_body},
        status=status,
        error=None if status == "success" else f"HTTP {resp.status_code}",
    )
