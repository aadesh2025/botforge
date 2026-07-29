"""Campaign CRUD. Broadcast sending is deliberately not implemented — see ADR-039."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.models import Agent, Campaign
from app.modules.campaigns import schemas
from app.modules.orgs.deps import OrgContext


def _out(row: Campaign) -> schemas.CampaignOut:
    return schemas.CampaignOut(
        id=row.id,
        agent_id=row.agent_id,
        kind=row.kind,
        name=row.name,
        message=row.message,
        trigger_config=row.trigger_config,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get(session: AsyncSession, ctx: OrgContext, campaign_id: uuid.UUID) -> Campaign:
    row = await session.get(Campaign, campaign_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("campaigns.not_found", "Campaign not found.", 404)
    return row


def _guard_broadcast(kind: str, status: str | None) -> None:
    """Broadcasts stay drafts until the compliance work exists (ADR-039).

    Consent tracking, an unsubscribe path, rate-limited batch sending and WhatsApp template
    origination are all prerequisites. Activating one without them risks a banned number and
    messaging people who never opted in.
    """
    if kind == "broadcast" and status in ("active", "paused"):
        raise AppError(
            "campaigns.broadcast_disabled",
            "Outbound broadcasts can't be activated yet: contact consent, unsubscribe "
            "handling and rate-limited sending aren't built. Save it as a draft.",
            400,
        )


async def list_campaigns(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None = None
) -> list[schemas.CampaignOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(Campaign)
        .where(Campaign.organization_id == ctx.org.id)
        .order_by(Campaign.created_at.desc())
    )
    if agent_id is not None:
        stmt = stmt.where(Campaign.agent_id == agent_id)
    return [_out(r) for r in (await session.execute(stmt)).scalars().all()]


async def create_campaign(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateCampaignRequest
) -> schemas.CampaignOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    _guard_broadcast(data.kind, data.status)
    agent = await session.get(Agent, data.agent_id)
    if agent is None or agent.organization_id != ctx.org.id:
        raise AppError("agents.not_found", "Agent not found.", 404)

    row = Campaign(
        organization_id=ctx.org.id,
        agent_id=data.agent_id,
        kind=data.kind,
        name=data.name,
        message=data.message,
        trigger_config=data.trigger_config,
        status=data.status,
    )
    session.add(row)
    await session.flush()
    return _out(row)


async def update_campaign(
    session: AsyncSession, ctx: OrgContext, campaign_id: uuid.UUID, data: schemas.UpdateCampaignRequest
) -> schemas.CampaignOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    row = await _get(session, ctx, campaign_id)
    _guard_broadcast(row.kind, data.status)
    if data.name is not None:
        row.name = data.name
    if data.message is not None:
        row.message = data.message
    if data.trigger_config is not None:
        row.trigger_config = data.trigger_config
    if data.status is not None:
        row.status = data.status
    await session.flush()
    return _out(row)


async def delete_campaign(session: AsyncSession, ctx: OrgContext, campaign_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    row = await _get(session, ctx, campaign_id)
    await session.delete(row)


async def active_widget_campaigns(session: AsyncSession, agent: Agent) -> list[schemas.PublicCampaign]:
    """Active widget triggers for the public config. Broadcasts never appear here."""
    stmt = (
        select(Campaign)
        .where(
            Campaign.agent_id == agent.id,
            Campaign.kind == "widget_trigger",
            Campaign.status == "active",
        )
        .order_by(Campaign.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        schemas.PublicCampaign(
            id=r.id,
            message=r.message,
            delay_seconds=int(r.trigger_config.get("delay_seconds", 10) or 10),
            url_pattern=str(r.trigger_config.get("url_pattern") or "") or None,
        )
        for r in rows
    ]
