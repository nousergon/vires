"""Add user_settings.feed_token for the public ICS calendar feed.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-28

NOTE: autogenerate also proposes dropping the exercises_fts* shadow tables (SQLite
FTS5, managed by api/db/fts.py, not the ORM) — intentionally omitted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("feed_token", sa.String(), nullable=True))
    op.create_index(
        "ix_user_settings_feed_token", "user_settings", ["feed_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_user_settings_feed_token", table_name="user_settings")
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.drop_column("feed_token")
