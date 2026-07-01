"""Athletic calendar: calendar_events (vires-ops#31).

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-01

Adds ``CalendarEvent``: an external athletic event (race, weekly league,
recreation, travel, rehab window) the coach trains *around* — distinct from
``objectives``, which the coach peaks *toward* (see vires-ops#30 for why these
must not be merged). ``load`` is a small structured JSON sub-object
(regions/intensity/duration_min), the same JSON-column precedent as
``objectives.demands_profile``. ``recurrence='weekly'`` events are stored as a
single row; concrete occurrences are expanded server-side on read (never
persisted — see ``api.services.calendar_events``), so this migration has no
occurrence-table counterpart.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sport", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_end_date", sa.Date(), nullable=True),
        sa.Column(
            "recurrence", sa.String(), nullable=False, server_default="none"
        ),
        sa.Column("load", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("objective_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["objective_id"], ["objectives.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_calendar_events_tenant_id", "calendar_events", ["tenant_id"])
    op.create_index("ix_calendar_events_user_id", "calendar_events", ["user_id"])
    op.create_index(
        "ix_calendar_events_objective_id", "calendar_events", ["objective_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_objective_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_user_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_tenant_id", table_name="calendar_events")
    op.drop_table("calendar_events")
