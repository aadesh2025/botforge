"""Remove ephemeral dev/test data from a local database.

Throwaway rows accumulate in the dev DB from manual testing and the Playwright E2E suite
(every fixture account uses an ``@example.com`` email — the seed uses ``@botforge.local`` and
the ``demo`` slug, so the two never overlap). This utility deletes:

  * the ``live_demo`` feature flag created during Phase 17 testing,
  * every ``@example.com`` user and the organizations they created (org FKs cascade, so all
    agents/conversations/channels/etc. under those orgs go with them).

It is **idempotent** and only ever touches ``@example.com`` accounts + the named flag — it can
never delete seed data or a real tenant. Run it with::

    uv run python -m app.db.cleanup_devdata          # delete
    uv run python -m app.db.cleanup_devdata --dry-run  # report only

Nuke-everything alternative (also clears throwaway rows): ``alembic downgrade base &&
alembic upgrade head && python -m app.db.seed``.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.core.logging import configure_logging, get_logger
from app.db.session import SessionFactory

log = get_logger("db.cleanup")

TEST_EMAIL_PATTERN = "%@example.com"

# Nullable, no-cascade user references. Nulled before deleting users so a stray cross-org
# reference can never block the delete. (All test content normally lives in deleted orgs.)
_USER_REF_COLUMNS: list[tuple[str, str]] = [
    ("agents", "created_by"),
    ("agent_versions", "created_by"),
    ("tools", "created_by"),
    ("channels", "created_by"),
    ("knowledge_bases", "created_by"),
    ("documents", "created_by"),
    ("conversations", "assigned_to"),
    ("handoffs", "assigned_to"),
    ("invitations", "invited_by"),
    ("audit_logs", "actor_user_id"),
]


async def cleanup(dry_run: bool = False) -> dict[str, int]:
    async with SessionFactory() as session:
        users = (
            await session.execute(text("SELECT count(*) FROM users WHERE email LIKE :p"), {"p": TEST_EMAIL_PATTERN})
        ).scalar_one()
        orgs = (
            await session.execute(
                text(
                    "SELECT count(*) FROM organizations WHERE created_by IN "
                    "(SELECT id FROM users WHERE email LIKE :p)"
                ),
                {"p": TEST_EMAIL_PATTERN},
            )
        ).scalar_one()
        flags = (await session.execute(text("SELECT count(*) FROM feature_flags WHERE key = 'live_demo'"))).scalar_one()

        counts = {"users": int(users), "orgs": int(orgs), "live_demo_flags": int(flags)}
        if dry_run:
            log.info("cleanup_dry_run", **counts)
            return counts

        # 1. The named Phase-17 test flag.
        await session.execute(text("DELETE FROM feature_flags WHERE key = 'live_demo'"))
        # 2. Orgs created by test users → cascades to all their agents/conversations/etc.
        await session.execute(
            text("DELETE FROM organizations WHERE created_by IN (SELECT id FROM users WHERE email LIKE :p)"),
            {"p": TEST_EMAIL_PATTERN},
        )
        # 3. Defensively clear any lingering no-cascade references to the doomed users.
        for tbl, col in _USER_REF_COLUMNS:
            await session.execute(
                text(f"UPDATE {tbl} SET {col} = NULL WHERE {col} IN (SELECT id FROM users WHERE email LIKE :p)"),
                {"p": TEST_EMAIL_PATTERN},
            )
        # 4. Delete the test users themselves (sessions/oauth/memberships cascade on user_id).
        await session.execute(text("DELETE FROM users WHERE email LIKE :p"), {"p": TEST_EMAIL_PATTERN})
        await session.commit()

        log.info("cleanup_done", **counts)
        return counts


if __name__ == "__main__":
    configure_logging()
    result = asyncio.run(cleanup(dry_run="--dry-run" in sys.argv))
    print(f"cleanup: {result}")
