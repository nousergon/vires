"""Season foundation: objective multi-day events + planned-workout attribution.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-29

Adds ``objectives.event_end_date`` (a multi-day event's last day; training is
skipped target_date..event_end_date and the next block starts after it) and
``planned_workouts.objective_id`` (which objective's training block a day
prepares for). Both nullable; ``objective_id`` is SET NULL on objective delete.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.add_column(sa.Column("event_end_date", sa.Date(), nullable=True))

    with op.batch_alter_table("planned_workouts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("objective_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_planned_workouts_objective_id", ["objective_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_planned_workouts_objective_id",
            "objectives",
            ["objective_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("planned_workouts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_planned_workouts_objective_id", type_="foreignkey")
        batch_op.drop_index("ix_planned_workouts_objective_id")
        batch_op.drop_column("objective_id")

    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.drop_column("event_end_date")
