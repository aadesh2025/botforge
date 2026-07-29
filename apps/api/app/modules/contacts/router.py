"""Contacts CRM routes under /v1/contacts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.contacts import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/contacts", tags=["contacts"])


@router.get("", response_model=schemas.ContactListOut)
async def list_contacts(
    q: str | None = Query(default=None, description="Match a display name or platform id."),
    lead_stage: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    label: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ContactListOut:
    return await service.list_contacts(
        session,
        ctx,
        query=q,
        lead_stage=lead_stage,
        channel=channel,
        label=label,
        limit=limit,
        offset=offset,
    )


@router.get("/{contact_id}", response_model=schemas.ContactDetail)
async def get_contact(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ContactDetail:
    return await service.get_contact(session, ctx, contact_id)


@router.patch("/{contact_id}", response_model=schemas.ContactDetail)
async def update_contact(
    contact_id: uuid.UUID,
    data: schemas.UpdateContactRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ContactDetail:
    return await service.update_contact(session, ctx, contact_id, data)


@router.patch("/{contact_id}/labels", response_model=schemas.ContactDetail)
async def set_labels(
    contact_id: uuid.UUID,
    data: schemas.LabelsRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ContactDetail:
    return await service.set_labels(session, ctx, contact_id, data.labels)


@router.post("/{contact_id}/notes", response_model=schemas.ContactDetail)
async def add_note(
    contact_id: uuid.UUID,
    data: schemas.NoteRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ContactDetail:
    return await service.add_note(session, ctx, contact_id, data.text)
