"""Execution of MCP-bound tools (docs/17 Phase 1 §4).

Config shape (Tool.config): {"server_id": "...", "tool_name": "..."}. The server row (org-
scoped, credentials encrypted) is looked up fresh on every call and checked against the
calling org — mirrors ADR-055/047/048: a server is never resolved against the wrong tenant,
even if a `Tool` row somehow carried another org's `server_id`.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.models import MCPServer, User
from app.tools.base import ToolResult
from app.tools.mcp_client import MCPServerConfig, MCPToolError, call_tool


def server_config(server: MCPServer) -> MCPServerConfig:
    auth: dict[str, Any] = {}
    if server.auth_config_enc:
        try:
            auth = json.loads(decrypt(server.auth_config_enc))
        except (ValueError, TypeError):
            auth = {}
    return MCPServerConfig(
        transport=server.transport,
        url_or_command=server.url_or_command,
        args=auth.get("args"),
        env=auth.get("env"),
        headers=auth.get("headers"),
    )


async def resolve_server_config(session: AsyncSession, server: MCPServer) -> MCPServerConfig:
    """`server_config` plus the stdio permission: only a server registered by platform staff may
    spawn a subprocess. Checked at connect time, not just at registration, so a stdio row created
    before that rule existed (or by a since-demoted user) stops running."""
    config = server_config(server)
    if server.transport == "stdio" and server.created_by is not None:
        creator = await session.get(User, server.created_by)
        config.stdio_allowed = bool(creator and creator.is_staff)
    return config


async def execute_mcp_tool(
    session: AsyncSession, org_id: UUID, config: dict[str, Any], args: dict[str, Any]
) -> ToolResult:
    server_id = config.get("server_id")
    tool_name = config.get("tool_name")
    if not server_id or not tool_name:
        return ToolResult(output={}, status="error", error="MCP tool is missing server_id/tool_name")

    server = await session.get(MCPServer, UUID(str(server_id)))
    if server is None or server.organization_id != org_id:
        return ToolResult(output={}, status="error", error="MCP server not found for this organization")
    if not server.enabled:
        return ToolResult(output={}, status="error", error=f"MCP server '{server.name}' is disabled")

    try:
        output = await call_tool(await resolve_server_config(session, server), str(tool_name), args)
    except MCPToolError as exc:
        return ToolResult(output={}, status="error", error=str(exc))
    return ToolResult(output=output, status="success")
