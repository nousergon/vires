"""user settings

Revision ID: 25fc1590293f
Revises: a785c819fa5f
Create Date: 2026-06-27 12:21:55.599507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25fc1590293f'
down_revision: Union[str, Sequence[str], None] = 'a785c819fa5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('weight_unit', sa.String(), nullable=False),
        sa.Column('default_rest_seconds', sa.Integer(), nullable=False),
        sa.Column('default_sets', sa.Integer(), nullable=False),
        sa.Column('default_reps', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_user_settings_tenant_id'), ['tenant_id'], unique=False
        )
    # NOTE: the autogenerate also proposed dropping the exercises_fts* tables —
    # those are SQLite FTS5 shadow tables (not in ORM metadata). Intentionally
    # omitted; they are managed by api/db/fts.py, not alembic.


def downgrade() -> None:
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_settings_tenant_id'))
    op.drop_table('user_settings')
