"""Per-workout tracking: tags, pre-workout fuel, end-of-session energy/intensity.

Revision ID: f2a3b4c5d6e7
Revises: de8061df9f96
Create Date: 2026-07-03

Adds four columns to ``workout_sessions`` (both strength and activity sessions):

* ``tags`` — free-text JSON list of labels, mixing reusable tags and one-off
  custom inputs, set/edited while the session is open.
* ``pre_workout_fuel`` — free text: food/drink/supplements taken before training.
* ``energy_level`` / ``workout_intensity`` — 1–10 self-report captured at finish
  (how the body felt vs. how hard the session was). Named ``workout_intensity``
  to stay distinct from ``activity_details.intensity`` (light/moderate/hard).

All nullable / defaulted; existing rows read back as ``tags=[]`` and the rest
``NULL``. ``started_at`` (workout start time) already existed and is unchanged.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "de8061df9f96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tags", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("pre_workout_fuel", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("energy_level", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("workout_intensity", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_column("workout_intensity")
        batch_op.drop_column("energy_level")
        batch_op.drop_column("pre_workout_fuel")
        batch_op.drop_column("tags")
