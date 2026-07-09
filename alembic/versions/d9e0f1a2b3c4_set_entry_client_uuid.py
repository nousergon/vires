"""Add set_entries.client_uuid for offline-first idempotent set logging.

Revision ID: d9e0f1a2b3c4
Revises: b3c4d5e6f7a8
Create Date: 2026-07-09

Backs vires-ops#48 (PWA offline-first set logging). The PWA mints a
``crypto.randomUUID()`` per logged set BEFORE the write, queues it in IndexedDB
while offline, and replays it on reconnect. The unique index on
(session_exercise_id, client_uuid) makes replay idempotent — re-POSTing the same
UUID returns the existing row rather than appending a duplicate. Nullable so
online writes and every pre-existing row need no UUID; SQLite (and Postgres)
treat multiple NULLs as distinct, so unlabeled rows never collide.

NOTE: autogenerate also proposes dropping the exercises_fts* shadow tables
(SQLite FTS5, managed by api/db/fts.py, not the ORM) — intentionally omitted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER-ADD a column that participates in a
    # new table-level UniqueConstraint in place, so Alembic rebuilds the table.
    with op.batch_alter_table("set_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("client_uuid", sa.String(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_set_entries_se_client_uuid",
            ["session_exercise_id", "client_uuid"],
        )


def downgrade() -> None:
    with op.batch_alter_table("set_entries", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_set_entries_se_client_uuid", type_="unique"
        )
        batch_op.drop_column("client_uuid")
