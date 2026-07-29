"""Help Center articles — public-facing docs a visitor can browse.

Deliberately a separate store from the RAG `Document`: Knowledge is retrieval material for
the model, this is prose a human reads. An article can *also* be pushed into a knowledge
base (opt-in per article) so the agent can answer from it — see `sync_to_kb`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class HelpArticle(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "help_articles"
    __table_args__ = (
        # Slugs address articles in public URLs, so they must be unique per agent.
        Index("ix_help_articles_agent_slug", "agent_id", "slug", unique=True),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Opt-in: also feed this article to the agent's knowledge base on publish.
    sync_to_kb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: The RAG document created by that sync, so re-publishing replaces rather than duplicates.
    kb_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
