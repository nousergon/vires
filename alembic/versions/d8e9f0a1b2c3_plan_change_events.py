"""Plan-change audit: plan_change_events.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-29

One row per automatic plan mutation — the deterministic per-workout
autoregulation (micro loop) and the applied macro re-plan / revision — so "why
did my plan change?" is answerable. ``program_id`` / ``session_id`` are SET NULL
on delete so the audit trail outlives the rows it references.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["workout_sessions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_plan_change_events_tenant_id", "plan_change_events", ["tenant_id"]
    )
    op.create_index("ix_plan_change_events_user_id", "plan_change_events", ["user_id"])
    op.create_index(
        "ix_plan_change_events_program_id", "plan_change_events", ["program_id"]
    )
    op.create_index(
        "ix_plan_change_events_created_at", "plan_change_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_plan_change_events_created_at", "plan_change_events")
    op.drop_index("ix_plan_change_events_program_id", "plan_change_events")
    op.drop_index("ix_plan_change_events_user_id", "plan_change_events")
    op.drop_index("ix_plan_change_events_tenant_id", "plan_change_events")
    op.drop_table("plan_change_events")
