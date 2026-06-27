"""target_weight on template+session exercises

Revision ID: 312bbf0caadb
Revises: 25fc1590293f
Create Date: 2026-06-27 15:08:11.101213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '312bbf0caadb'
down_revision: Union[str, Sequence[str], None] = '25fc1590293f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: autogenerate also proposed dropping the exercises_fts* tables — those
    # are SQLite FTS5 shadow tables (managed by api/db/fts.py, not the ORM).
    # Intentionally omitted.
    with op.batch_alter_table('session_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_weight', sa.Float(), nullable=True))
    with op.batch_alter_table('template_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_weight', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('template_exercises', schema=None) as batch_op:
        batch_op.drop_column('target_weight')
    with op.batch_alter_table('session_exercises', schema=None) as batch_op:
        batch_op.drop_column('target_weight')
