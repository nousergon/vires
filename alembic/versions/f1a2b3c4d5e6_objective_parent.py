"""Sub-objectives: ``objectives.parent_objective_id`` (self-referential).

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-06-30

Adds a nullable self-FK so an objective can be a *sub-objective* (a dated
training milestone) of a larger parent objective — e.g. "Mailbox Peak" nested
under "Climb Baker". A sub-objective is NOT a focus-eligible peak of its own
(see ``api.services.objective_focus``): it informs the parent's periodization as
a mid-block benchmark and counts as training credit toward the parent. ``SET
NULL`` so deleting the parent leaves the milestone as a standalone objective
rather than destroying it. Indexed for the children lookup.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table so SQLite (no native ALTER ... ADD CONSTRAINT) rebuilds
    # the table with the new self-referential FK + index.
    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("parent_objective_id", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            "ix_objectives_parent_objective_id", ["parent_objective_id"]
        )
        batch_op.create_foreign_key(
            "fk_objectives_parent_objective_id",
            "objectives",
            ["parent_objective_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("objectives", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_objectives_parent_objective_id", type_="foreignkey"
        )
        batch_op.drop_index("ix_objectives_parent_objective_id")
        batch_op.drop_column("parent_objective_id")
