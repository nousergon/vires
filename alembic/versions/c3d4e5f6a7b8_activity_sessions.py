"""generic activity sessions: session_type='activity' + activity_details

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-02

Adds ``ActivityDetail``: a generic cross-training session (climbing, swimming,
yoga, ...) whose coarse structured load (regions/intensity) reuses the same
vocabulary already established for athletic-calendar events
(``CalendarEvent.load``, vires-ops#33) rather than inventing a bespoke schema
per activity. See ``api.db.models.ActivityDetail`` docstring for the full
rationale.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_details",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "template_key", sa.String(), nullable=False, server_default="custom"
        ),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("regions", sa.String(), nullable=False, server_default="full"),
        sa.Column(
            "intensity", sa.String(), nullable=False, server_default="moderate"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_activity_details_session_id"),
        "activity_details",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_activity_details_session_id"), table_name="activity_details"
    )
    op.drop_table("activity_details")
