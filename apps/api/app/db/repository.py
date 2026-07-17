"""Repository base enforcing tenant isolation.

Every query a repository builds is filtered by ``organization_id`` at the query layer
(CLAUDE.md §8), so a repository bound to one org can never read or count another org's rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


@dataclass(slots=True)
class Page(Generic[ModelT]):
    items: Sequence[ModelT]
    total: int
    limit: int
    offset: int


class BaseRepository(Generic[ModelT]):
    """Tenant-scoped data access for a single model."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    def _org_column(self) -> Any:
        return self.model.organization_id  # type: ignore[attr-defined]

    def _id_column(self) -> Any:
        return self.model.id  # type: ignore[attr-defined]

    def scoped(self) -> Select[tuple[ModelT]]:
        """A SELECT already filtered to this repository's organization."""
        return select(self.model).where(self._org_column() == self.organization_id)

    async def get(self, obj_id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(self.scoped().where(self._id_column() == obj_id))
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 50, offset: int = 0) -> Page[ModelT]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        items = (await self.session.execute(self.scoped().limit(limit).offset(offset))).scalars().all()
        total = await self.count()
        return Page(items=items, total=total, limit=limit, offset=offset)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model).where(
            self._org_column() == self.organization_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    def add(self, obj: ModelT) -> ModelT:
        """Stamp the org id and stage the object for insert."""
        obj.organization_id = self.organization_id  # type: ignore[attr-defined]
        self.session.add(obj)
        return obj
