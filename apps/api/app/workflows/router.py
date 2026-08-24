"""Workflow routes (docs/17 Phase 2 §10). Three routers because the paths don't share one
prefix: agent-scoped creation/listing, workflow-id-scoped everything else, and run-id-scoped
resume/cancel/steps — mirrors `app/modules/agents/router.py`'s split for `templates_router`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.orgs.deps import OrgContext, current_org
from app.workflows import schemas, service

agent_workflows_router = APIRouter(prefix="/v1/agents/{agent_id}/workflows", tags=["workflows"])
router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
runs_router = APIRouter(prefix="/v1/workflow-runs", tags=["workflows"])


@agent_workflows_router.post("", response_model=schemas.WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_agent_workflow(
    agent_id: uuid.UUID,
    data: schemas.CreateWorkflowRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowOut:
    return await service.create_workflow(session, ctx, agent_id, data)


@agent_workflows_router.get("", response_model=list[schemas.WorkflowOut])
async def list_agent_workflows(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowOut]:
    return await service.list_workflows(session, ctx, agent_id)


@router.get("/{workflow_id}", response_model=schemas.WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowOut:
    return await service.get_workflow(session, ctx, workflow_id)


@router.patch("/{workflow_id}", response_model=schemas.WorkflowOut)
async def update_workflow(
    workflow_id: uuid.UUID,
    data: schemas.UpdateWorkflowRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowOut:
    return await service.update_workflow(session, ctx, workflow_id, data)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_workflow(session, ctx, workflow_id)


@router.post(
    "/{workflow_id}/versions", response_model=schemas.WorkflowVersionOut, status_code=status.HTTP_201_CREATED
)
async def create_version(
    workflow_id: uuid.UUID,
    data: schemas.CreateWorkflowVersionRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowVersionOut:
    return await service.create_version(session, ctx, workflow_id, data)


@router.get("/{workflow_id}/versions", response_model=list[schemas.WorkflowVersionOut])
async def list_versions(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowVersionOut]:
    return await service.list_versions(session, ctx, workflow_id)


@router.post("/{workflow_id}/versions/{version}/publish", response_model=schemas.WorkflowOut)
async def publish_version(
    workflow_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowOut:
    return await service.publish_version(session, ctx, workflow_id, version)


@router.post("/{workflow_id}/run", response_model=schemas.WorkflowRunOut, status_code=status.HTTP_201_CREATED)
async def run_workflow(
    workflow_id: uuid.UUID,
    data: schemas.RunWorkflowRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowRunOut:
    """Runs the workflow's PUBLISHED version. Dispatches to Celery in production and returns
    immediately with `status: "running"` — poll `GET /v1/workflow-runs/{id}/steps` (or the
    run itself) for progress. A response of `"paused_approval"` only appears once a real
    worker has actually reached that far."""
    return await service.run_workflow_now(session, ctx, workflow_id, data)


@router.post(
    "/{workflow_id}/test-run", response_model=schemas.WorkflowRunOut, status_code=status.HTTP_201_CREATED
)
async def test_run_workflow(
    workflow_id: uuid.UUID,
    data: schemas.RunWorkflowRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowRunOut:
    """Runs the workflow's LATEST version — draft or published — marked `is_test=True`.
    Requires only `WORKFLOWS_WRITE`, not `WORKFLOWS_PUBLISH`: testing a draft is part of
    authoring it (docs/17 Phase 2 item 3)."""
    return await service.run_workflow_test(session, ctx, workflow_id, data)


@runs_router.get("/{run_id}", response_model=schemas.WorkflowRunOut)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowRunOut:
    return await service.get_workflow_run(session, ctx, run_id)


@runs_router.post("/{run_id}/resume", response_model=schemas.WorkflowRunOut)
async def resume_run(
    run_id: uuid.UUID,
    data: schemas.ResumeWorkflowRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowRunOut:
    return await service.resume_workflow_run(session, ctx, run_id, data)


@runs_router.post("/{run_id}/cancel", response_model=schemas.WorkflowRunOut)
async def cancel_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.WorkflowRunOut:
    return await service.cancel_workflow_run(session, ctx, run_id)


@runs_router.get("/{run_id}/steps", response_model=list[schemas.WorkflowStepOut])
async def list_run_steps(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.WorkflowStepOut]:
    return await service.list_run_steps(session, ctx, run_id)
