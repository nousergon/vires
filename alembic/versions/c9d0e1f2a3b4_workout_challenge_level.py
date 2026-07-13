"""workout_sessions.challenge_level — end-of-workout challenge self-report.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-13

Adds ``challenge_level`` to ``workout_sessions``: a 1-10 self-report captured
at finish (same prompt as ``energy_level``/``workout_intensity``), answering
"was this appropriately challenging for you" — distinct from
``workout_intensity`` (raw physical effort/RPE) and from ``energy_level``
(readiness/how the body felt going in). Nullable/defaulted like its two
siblings from f2a3b4c5d6e7_workout_session_tracking; existing rows read back
as ``NULL``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("challenge_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_column("challenge_level")
