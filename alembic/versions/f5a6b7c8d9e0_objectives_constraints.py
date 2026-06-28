"""Objective-driven coaching: objectives + training_constraints.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-28

Adds the two entities behind the objective-driven coach (build spec): an
``Objective`` the program peaks/tapers toward and a ``Constraint`` the coach
trains *around*. Both are user-owned. The ``objectives`` partial unique index
guarantees at most one active *primary* objective per (tenant, user) — the
structural backstop behind the app-level demote-on-set logic.

NOTE: alembic autogenerate would also propose dropping the exercises_fts* tables
— those are SQLite FTS5 shadow tables (managed by api/db/fts.py, not the ORM).
Intentionally omitted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "objectives",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="dated"),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("sport", sa.String(), nullable=True),
        sa.Column("demands_profile", sa.JSON(), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_objectives_tenant_id", "objectives", ["tenant_id"])
    op.create_index("ix_objectives_user_id", "objectives", ["user_id"])
    op.create_index("ix_objectives_is_primary", "objectives", ["is_primary"])
    # At most one primary objective per (tenant, user).
    op.create_index(
        "uq_one_primary_objective_per_user",
        "objectives",
        ["tenant_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("is_primary = 1"),
    )

    op.create_table(
        "training_constraints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("directives", sa.Text(), nullable=True),
        sa.Column(
            "defer_to_professional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_training_constraints_tenant_id", "training_constraints", ["tenant_id"]
    )
    op.create_index(
        "ix_training_constraints_user_id", "training_constraints", ["user_id"]
    )
    op.create_index(
        "ix_training_constraints_is_active", "training_constraints", ["is_active"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_constraints_is_active", table_name="training_constraints"
    )
    op.drop_index(
        "ix_training_constraints_user_id", table_name="training_constraints"
    )
    op.drop_index(
        "ix_training_constraints_tenant_id", table_name="training_constraints"
    )
    op.drop_table("training_constraints")

    op.drop_index("uq_one_primary_objective_per_user", table_name="objectives")
    op.drop_index("ix_objectives_is_primary", table_name="objectives")
    op.drop_index("ix_objectives_user_id", table_name="objectives")
    op.drop_index("ix_objectives_tenant_id", table_name="objectives")
    op.drop_table("objectives")
