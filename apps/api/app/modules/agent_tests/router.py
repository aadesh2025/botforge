"""Agent regression testing routes (docs/17 Phase 3, ADR-079).

Three routers because the paths don't share one prefix: agent-scoped test CRUD + running,
agent-scoped run history, and run-id-scoped single lookup — mirrors `app/workflows/router.py`'s
identical three-router split for the same reason.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.agent_tests import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

tests_router = APIRouter(prefix="/v1/agents/{agent_id}/tests", tags=["agent-tests"])
test_runs_by_agent_router = APIRouter(prefix="/v1/agents/{agent_id}/test-runs", tags=["agent-tests"])
test_run_router = APIRouter(prefix="/v1/agent-test-runs", tags=["agent-tests"])


@tests_router.post("", response_model=schemas.AgentTestOut, status_code=status.HTTP_201_CREATED)
async def create_test(
    agent_id: uuid.UUID,
    data: schemas.CreateAgentTestRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.AgentTestOut:
    return await service.create_agent_test(session, ctx, agent_id, data)


@tests_router.get("", response_model=list[schemas.AgentTestOut])
async def list_tests(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.AgentTestOut]:
    return await service.list_agent_tests(session, ctx, agent_id)


@tests_router.post("/run", response_model=list[schemas.AgentTestRunOut], status_code=status.HTTP_201_CREATED)
async def run_tests(
    agent_id: uuid.UUID,
    data: schemas.RunAgentTestsRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.AgentTestRunOut]:
    """Runs every enabled test case for this agent (or just `test_ids`, if given) as one batch.
    `mode` defaults to `"cached"` — never live unless explicitly requested in the body."""
    return await service.run_agent_tests(session, ctx, agent_id, data)


@tests_router.patch("/{test_id}", response_model=schemas.AgentTestOut)
async def update_test(
    agent_id: uuid.UUID,
    test_id: uuid.UUID,
    data: schemas.UpdateAgentTestRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.AgentTestOut:
    return await service.update_agent_test(session, ctx, agent_id, test_id, data)


@tests_router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    agent_id: uuid.UUID,
    test_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_agent_test(session, ctx, agent_id, test_id)


@test_runs_by_agent_router.get("", response_model=list[schemas.AgentTestRunOut])
async def list_test_runs(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.AgentTestRunOut]:
    """Every test run for this agent, newest first — including every case in every batch."""
    return await service.list_agent_test_runs(session, ctx, agent_id)


@test_run_router.get("/{run_id}", response_model=schemas.AgentTestRunOut)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.AgentTestRunOut:
    return await service.get_agent_test_run(session, ctx, run_id)
