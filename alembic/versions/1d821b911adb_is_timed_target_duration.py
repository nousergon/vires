"""is_timed + target_duration

Revision ID: 1d821b911adb
Revises: 312bbf0caadb
Create Date: 2026-06-27 16:09:18.128893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d821b911adb'
down_revision: Union[str, Sequence[str], None] = '312bbf0caadb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: autogenerate also proposed dropping the exercises_fts* tables (SQLite
    # FTS5 shadow tables managed by api/db/fts.py) — intentionally omitted.
    with op.batch_alter_table('exercises', schema=None) as batch_op:
        # server_default so existing rows backfill to false; is_timed is then
        # synced from free-exercise-db force=="static" by the seed backfill.
        batch_op.add_column(
            sa.Column('is_timed', sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table('session_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_duration_seconds', sa.Integer(), nullable=True))
    with op.batch_alter_table('template_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_duration_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('template_exercises', schema=None) as batch_op:
        batch_op.drop_column('target_duration_seconds')
    with op.batch_alter_table('session_exercises', schema=None) as batch_op:
        batch_op.drop_column('target_duration_seconds')
    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.drop_column('is_timed')
