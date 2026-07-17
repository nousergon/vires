"""Exercise movement_pattern taxonomy

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-07-17

Adds ``exercises.movement_pattern`` (squat/hinge/horizontal_push/...) — see
api.db.exercise_taxonomy. Schema-only, like the 1d821b911adb is_timed column:
actual values are populated by ``backfill_movement_pattern`` in api/db/seed.py,
which runs on every ``python -m api.db.seed`` invocation (including the
idempotent post-migration step in infrastructure/deploy-on-merge.sh), so no
separate manual backfill step is needed on deploy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('movement_pattern', sa.String(), nullable=True))
        batch_op.create_index(
            'ix_exercises_movement_pattern', ['movement_pattern'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.drop_index('ix_exercises_movement_pattern')
        batch_op.drop_column('movement_pattern')
