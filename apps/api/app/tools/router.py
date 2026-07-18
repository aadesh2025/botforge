"""Tool routes under /v1/tools (docs/04 §Tools)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.orgs.deps import OrgContext, current_org
from app.tools import schemas, service

router = APIRouter(prefix="/v1/tools", tags=["tools"])


# Static paths first so they don't collide with /{tool_id}.
@router.get("/builtin", response_model=list[schemas.BuiltinToolOut])
async def list_builtins() -> list[schemas.BuiltinToolOut]:
    return service.list_builtins()


@router.get("/runs", response_model=list[schemas.ToolRunOut])
async def list_runs(
    conversation_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.ToolRunOut]:
    return await service.list_runs(session, ctx, conversation_id)


@router.get("", response_model=list[schemas.ToolOut])
async def list_tools(
    agent_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.ToolOut]:
    return await service.list_tools(session, ctx, agent_id)


@router.post("", response_model=schemas.ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(
    data: schemas.CreateToolRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ToolOut:
    return await service.create_tool(session, ctx, data)


@router.get("/{tool_id}", response_model=schemas.ToolOut)
async def get_tool(
    tool_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ToolOut:
    return await service.get_tool(session, ctx, tool_id)


@router.patch("/{tool_id}", response_model=schemas.ToolOut)
async def update_tool(
    tool_id: uuid.UUID,
    data: schemas.UpdateToolRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ToolOut:
    return await service.update_tool(session, ctx, tool_id, data)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_tool(session, ctx, tool_id)


@router.post("/{tool_id}/test", response_model=schemas.TestToolResponse)
async def test_tool(
    tool_id: uuid.UUID,
    data: schemas.TestToolRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.TestToolResponse:
    return await service.test_tool(session, ctx, tool_id, data)
