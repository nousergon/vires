"""planned_workout_reschedule_provenance

Revision ID: 52e681744f33
Revises: a7ad5d99b363
Create Date: 2026-07-02 08:24:10.350793

Adds ``PlannedWorkout.rescheduled_from`` — set (to the prior
``scheduled_date``) when ``api.services.reschedule`` auto-moves a missed day
forward, so the UI can render "moved from Thu 7/2". Purely additive/nullable;
existing rows simply read NULL (never rescheduled).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52e681744f33'
down_revision: Union[str, Sequence[str], None] = 'a7ad5d99b363'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("planned_workouts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rescheduled_from", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("planned_workouts", schema=None) as batch_op:
        batch_op.drop_column("rescheduled_from")
