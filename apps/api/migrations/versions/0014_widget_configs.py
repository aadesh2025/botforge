"""Widget config out of the versioned draft into its own always-live table

Revision ID: 0014_widget_configs
Revises: 0013_crm_contacts
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_widget_configs"
down_revision: str | None = "0013_crm_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "widget_configs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.UUID(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "theme",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_widget_configs_agent_id", "widget_configs", ["agent_id"], unique=True)

    # Seed from the version whose widget config is actually being served today: the
    # published one if there is one, else the newest draft. Picking the wrong one here would
    # silently change how a live widget looks.
    op.execute(
        """
        INSERT INTO widget_configs (id, agent_id, theme, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            a.id,
            COALESCE(v.persona -> 'widget', '{}'::jsonb),
            now(),
            now()
        FROM agents a
        JOIN LATERAL (
            SELECT av.persona
              FROM agent_versions av
             WHERE av.agent_id = a.id
             ORDER BY (av.id = a.current_version_id) DESC, av.version DESC
             LIMIT 1
        ) v ON TRUE
        WHERE a.deleted_at IS NULL
          AND v.persona -> 'widget' IS NOT NULL
        """
    )


def downgrade() -> None:
    # Put each agent's widget config back on every one of its versions' persona, so the
    # pre-migration read path (`_live_version().persona.widget`) finds it again.
    op.execute(
        """
        UPDATE agent_versions av
           SET persona = jsonb_set(
                   COALESCE(av.persona, '{}'::jsonb), '{widget}', w.theme, true
               )
          FROM widget_configs w
         WHERE w.agent_id = av.agent_id
           AND w.theme <> '{}'::jsonb
        """
    )
    op.drop_index("ix_widget_configs_agent_id", table_name="widget_configs")
    op.drop_table("widget_configs")
