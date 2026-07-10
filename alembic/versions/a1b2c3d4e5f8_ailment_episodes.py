"""Ailment episodes + daily check-ins for date-anchored injury tracking.

Revision ID: a1b2c3d4e5f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ailment_episodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("onset_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("resolved_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ailment_episodes_tenant_id", "ailment_episodes", ["tenant_id"])
    op.create_index("ix_ailment_episodes_user_id", "ailment_episodes", ["user_id"])
    op.create_index("ix_ailment_episodes_status", "ailment_episodes", ["status"])

    op.create_table(
        "ailment_check_ins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ailment_id",
            sa.Integer(),
            sa.ForeignKey("ailment_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_in_date", sa.Date(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ailment_check_ins_ailment_id", "ailment_check_ins", ["ailment_id"])
    op.create_index("ix_ailment_check_ins_check_in_date", "ailment_check_ins", ["check_in_date"])
    op.create_index(
        "uq_ailment_check_in_per_day",
        "ailment_check_ins",
        ["ailment_id", "check_in_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ailment_check_in_per_day", table_name="ailment_check_ins")
    op.drop_index("ix_ailment_check_ins_check_in_date", table_name="ailment_check_ins")
    op.drop_index("ix_ailment_check_ins_ailment_id", table_name="ailment_check_ins")
    op.drop_table("ailment_check_ins")
    op.drop_index("ix_ailment_episodes_status", table_name="ailment_episodes")
    op.drop_index("ix_ailment_episodes_user_id", table_name="ailment_episodes")
    op.drop_index("ix_ailment_episodes_tenant_id", table_name="ailment_episodes")
    op.drop_table("ailment_episodes")
