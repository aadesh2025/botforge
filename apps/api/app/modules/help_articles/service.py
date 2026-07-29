"""Help Center CRUD, plus the opt-in push of an article into the agent's knowledge base."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import Agent, AgentVersion, Document, HelpArticle
from app.modules.help_articles import schemas
from app.modules.knowledge import schemas as kb_schemas
from app.modules.knowledge import service as kb_service
from app.modules.orgs.deps import OrgContext

log = get_logger("help_articles")


def _out(row: HelpArticle) -> schemas.HelpArticleOut:
    return schemas.HelpArticleOut(
        id=row.id,
        agent_id=row.agent_id,
        title=row.title,
        slug=row.slug,
        body_markdown=row.body_markdown,
        category=row.category,
        published=row.published,
        sync_to_kb=row.sync_to_kb,
        kb_document_id=row.kb_document_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get(session: AsyncSession, ctx: OrgContext, article_id: uuid.UUID) -> HelpArticle:
    row = await session.get(HelpArticle, article_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("help.not_found", "Article not found.", 404)
    return row


async def _live_version(session: AsyncSession, agent: Agent) -> AgentVersion | None:
    if agent.current_version_id is not None:
        v = await session.get(AgentVersion, agent.current_version_id)
        if v is not None:
            return v
    stmt = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.version.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _sync_to_knowledge_base(
    session: AsyncSession, ctx: OrgContext, article: HelpArticle
) -> None:
    """Push a published article into a knowledge base the agent actually retrieves from.

    Targeting the agent's *configured* KB is the point: writing to a fresh KB nothing reads
    would look like it worked while changing nothing. If the agent has no RAG source yet,
    say so rather than silently doing nothing.
    """
    agent = await session.get(Agent, article.agent_id) if article.agent_id else None
    if agent is None or agent.organization_id != ctx.org.id:
        raise AppError("help.agent_not_found", "This article isn't attached to an agent.", 400)
    version = await _live_version(session, agent)
    rag = (version.rag_config if version else None) or {}
    kb_ids = [str(k) for k in (rag.get("knowledge_base_ids") or [])]
    if not kb_ids:
        raise AppError(
            "help.no_knowledge_base",
            "This agent has no knowledge base to sync into. Attach one on the agent's "
            "Knowledge tab, or turn off 'Also teach the AI'.",
            400,
        )

    # Replace rather than accumulate: re-publishing an edited article shouldn't leave the
    # old text retrievable alongside the new.
    if article.kb_document_id is not None:
        old = await session.get(Document, article.kb_document_id)
        if old is not None:
            await kb_service.delete_document(session, ctx, old.id)
        article.kb_document_id = None

    doc = await kb_service.create_document(
        session,
        ctx,
        uuid.UUID(kb_ids[0]),
        kb_schemas.CreateDocumentRequest(
            source_type="text",
            text=f"# {article.title}\n\n{article.body_markdown}",
            filename=f"help-{article.slug}.md",
        ),
    )
    article.kb_document_id = doc.id
    log.info("help_article_synced_to_kb", article=str(article.id), document=str(doc.id))


async def list_articles(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None = None
) -> list[schemas.HelpArticleOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(HelpArticle)
        .where(HelpArticle.organization_id == ctx.org.id)
        .order_by(HelpArticle.updated_at.desc())
    )
    if agent_id is not None:
        stmt = stmt.where(HelpArticle.agent_id == agent_id)
    return [_out(r) for r in (await session.execute(stmt)).scalars().all()]


async def get_article(
    session: AsyncSession, ctx: OrgContext, article_id: uuid.UUID
) -> schemas.HelpArticleOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return _out(await _get(session, ctx, article_id))


async def create_article(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateHelpArticleRequest
) -> schemas.HelpArticleOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    agent = await session.get(Agent, data.agent_id)
    if agent is None or agent.organization_id != ctx.org.id:
        raise AppError("agents.not_found", "Agent not found.", 404)

    row = HelpArticle(
        organization_id=ctx.org.id,
        agent_id=data.agent_id,
        title=data.title,
        slug=data.slug or schemas.slugify(data.title),
        body_markdown=data.body_markdown,
        category=data.category,
        published=data.published,
        sync_to_kb=data.sync_to_kb,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "help.duplicate_slug", f"'{row.slug}' is already used by another article.", 409
        ) from exc

    if row.published and row.sync_to_kb:
        await _sync_to_knowledge_base(session, ctx, row)
    return _out(row)


async def update_article(
    session: AsyncSession, ctx: OrgContext, article_id: uuid.UUID, data: schemas.UpdateHelpArticleRequest
) -> schemas.HelpArticleOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    row = await _get(session, ctx, article_id)
    fields = data.model_dump(exclude_unset=True)
    content_changed = False

    for key in ("title", "slug", "body_markdown", "category"):
        if key in fields and fields[key] is not None:
            if getattr(row, key) != fields[key]:
                content_changed = True
            setattr(row, key, fields[key])
    if "published" in fields and data.published is not None:
        row.published = data.published
    if "sync_to_kb" in fields and data.sync_to_kb is not None:
        row.sync_to_kb = data.sync_to_kb

    try:
        await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "help.duplicate_slug", f"'{row.slug}' is already used by another article.", 409
        ) from exc

    if row.published and row.sync_to_kb and (content_changed or row.kb_document_id is None):
        await _sync_to_knowledge_base(session, ctx, row)
    elif (not row.published or not row.sync_to_kb) and row.kb_document_id is not None:
        # Unpublished or opted out: the AI shouldn't keep answering from it.
        old = await session.get(Document, row.kb_document_id)
        if old is not None:
            await kb_service.delete_document(session, ctx, old.id)
        row.kb_document_id = None
        await session.flush()
    return _out(row)


async def delete_article(session: AsyncSession, ctx: OrgContext, article_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    row = await _get(session, ctx, article_id)
    if row.kb_document_id is not None:
        old = await session.get(Document, row.kb_document_id)
        if old is not None:
            await kb_service.delete_document(session, ctx, old.id)
    await session.delete(row)


# ── Public reads (no auth; keyed by the agent's public key) ──────────────────────
async def public_list(session: AsyncSession, agent: Agent) -> list[schemas.PublicHelpArticleSummary]:
    stmt = (
        select(HelpArticle)
        .where(
            HelpArticle.agent_id == agent.id,
            HelpArticle.published.is_(True),
        )
        .order_by(HelpArticle.category.asc().nulls_last(), HelpArticle.title.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        schemas.PublicHelpArticleSummary(
            title=r.title, slug=r.slug, category=r.category, updated_at=r.updated_at
        )
        for r in rows
    ]


async def public_get(session: AsyncSession, agent: Agent, slug: str) -> schemas.PublicHelpArticle:
    stmt = select(HelpArticle).where(
        HelpArticle.agent_id == agent.id,
        HelpArticle.slug == slug,
        HelpArticle.published.is_(True),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        # Unpublished and non-existent look the same from outside, deliberately.
        raise AppError("help.not_found", "Article not found.", 404)
    return schemas.PublicHelpArticle(
        title=row.title,
        slug=row.slug,
        category=row.category,
        updated_at=row.updated_at,
        body_markdown=row.body_markdown,
    )
