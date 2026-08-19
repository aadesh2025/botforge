"""MCP server registry routes under /v1/mcp (docs/17 Phase 1 §10, backend-only for now)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.orgs.deps import OrgContext, current_org
from app.tools import schemas, service

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


@router.get("/servers", response_model=list[schemas.MCPServerOut])
async def list_mcp_servers(
    session: AsyncSession = Depends(get_session), ctx: OrgContext = Depends(current_org)
) -> list[schemas.MCPServerOut]:
    return await service.list_mcp_servers(session, ctx)


@router.post("/servers", response_model=schemas.MCPServerOut, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    data: schemas.CreateMCPServerRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.MCPServerOut:
    return await service.create_mcp_server(session, ctx, data)


@router.post("/servers/{server_id}/test-connection", response_model=schemas.MCPTestConnectionResponse)
async def test_mcp_server_connection(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.MCPTestConnectionResponse:
    return await service.test_mcp_server_connection(session, ctx, server_id)
