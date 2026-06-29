"""Objective priority: rank among multiple concurrent objectives.

Revision ID: c7d8e9f0a1b2
Revises: a7b8c9d0e1f2
Create Date: 2026-06-29

Adds ``objectives.priority`` so a user can hold several objectives at once and
the coach can derive a *focus* (the next peak) deterministically — soonest
upcoming dated objective, ``is_primary`` as a manual override pin, ``priority``
as the tiebreak. ``is_primary`` and its partial unique index are retained
unchanged (now an optional manual override rather than the only signal).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "priority",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.drop_column("priority")
