"""ruck sessions: session_type discriminator + ruck_details

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows backfill to the strength MVP type.
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'session_type', sa.String(), nullable=False, server_default='strength'
            )
        )

    # 1:1 loaded-cardio detail for session_type == 'ruck'. SI units throughout.
    op.create_table(
        'ruck_details',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('pack_weight_kg', sa.Float(), nullable=False),
        sa.Column('bodyweight_kg', sa.Float(), nullable=False),
        sa.Column('distance_m', sa.Float(), nullable=True),
        sa.Column('elevation_gain_m', sa.Float(), nullable=True),
        sa.Column('duration_s', sa.Integer(), nullable=True),
        sa.Column('terrain', sa.String(), nullable=False, server_default='trail'),
        sa.Column('metabolic_cost_kj', sa.Float(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['workout_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
    )
    op.create_index(
        op.f('ix_ruck_details_session_id'), 'ruck_details', ['session_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ruck_details_session_id'), table_name='ruck_details')
    op.drop_table('ruck_details')
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('session_type')
