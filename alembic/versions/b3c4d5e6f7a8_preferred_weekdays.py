"""Add preferred_weekdays to user_settings.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f8
Create Date: 2026-07-08

Durable weekly-lifting day preference (e.g. ["monday", "thursday"]) so the
coach honors it on every generation without the user re-stating it each
conversation. Existing rows backfill to an empty list (no standing
preference — unchanged behavior).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "preferred_weekdays", sa.JSON(), nullable=False, server_default="[]"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.drop_column("preferred_weekdays")
