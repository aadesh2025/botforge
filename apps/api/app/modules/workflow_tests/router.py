"""Workflow regression testing routes (docs/17 Phase 4 follow-up, ADR-081).

Three routers, mirroring `app/modules/agent_tests/router.py`'s identical split for the same
reason: workflow-scoped test CRUD + running, workflow-scoped run history, and run-id-scoped
single lookup.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.orgs.deps import OrgContext, current_org
from app.modules.workflow_tests import schemas, service

tests_router = APIRouter(prefix="/v1/workflows/{workflow_id}/tests", tags=["workflow-tests"])
test_runs_by_workflow_router = APIRouter(prefix="/v1/workflows/{workflow_id}/test-runs", tags=["workflow-tests"])
test_run_router = APIRouter(prefix="/v1/workflow-test-runs", tags=["workflow-tests"])


@tests_router.post("", response_model=schemas.WorkflowTestOut, status_code=status.HTTP_201_CREATED)
async def create_test(
    workflow_id: uuid.UUID,
    data: schemas.CreateWorkflowTestRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowTestOut:
    return await service.create_workflow_test(session, ctx, workflow_id, data)


@tests_router.get("", response_model=list[schemas.WorkflowTestOut])
async def list_tests(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowTestOut]:
    return await service.list_workflow_tests(session, ctx, workflow_id)


@tests_router.post("/run", response_model=list[schemas.WorkflowTestRunOut], status_code=status.HTTP_201_CREATED)
async def run_tests(
    workflow_id: uuid.UUID,
    data: schemas.RunWorkflowTestsRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowTestRunOut]:
    """Runs every enabled test case for this workflow (or just `test_ids`) as one batch, against
    the workflow's LATEST version (draft or published). `mode` defaults to `"cached"` — never
    live unless explicitly requested in the body."""
    return await service.run_workflow_tests(session, ctx, workflow_id, data)


@tests_router.patch("/{test_id}", response_model=schemas.WorkflowTestOut)
async def update_test(
    workflow_id: uuid.UUID,
    test_id: uuid.UUID,
    data: schemas.UpdateWorkflowTestRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowTestOut:
    return await service.update_workflow_test(session, ctx, workflow_id, test_id, data)


@tests_router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    workflow_id: uuid.UUID,
    test_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_workflow_test(session, ctx, workflow_id, test_id)


@test_runs_by_workflow_router.get("", response_model=list[schemas.WorkflowTestRunOut])
async def list_test_runs(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowTestRunOut]:
    """Every test run for this workflow, newest first — including every case in every batch."""
    return await service.list_workflow_test_runs(session, ctx, workflow_id)


@test_run_router.get("/{run_id}", response_model=schemas.WorkflowTestRunOut)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowTestRunOut:
    return await service.get_workflow_test_run(session, ctx, run_id)
