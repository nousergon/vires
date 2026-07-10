"""Fold pre_workout_fuel into tags, then drop the column.

Revision ID: e1f2a3b4c5d7
Revises: d9e0f1a2b3c4
Create Date: 2026-07-10

``pre_workout_fuel`` (free text: "black coffee, 5g creatine, banana") is
superseded by the existing ``tags`` list — the app now expects each item
(coffee, creatine, ...) logged as its own tag rather than a separate
free-text field. This migration is a one-time, best-effort backfill: for
every session with a non-blank ``pre_workout_fuel``, split it on commas/
semicolons and append any not-already-present fragment to ``tags``, then
drop the column. Downgrade re-adds the column empty (NULL) — the original
free text can't be losslessly reconstructed from the now-merged tags, so
this migration is one-way in practice.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d7"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_sessions = sa.table(
    "workout_sessions",
    sa.column("id", sa.Integer()),
    sa.column("tags", sa.JSON()),
    sa.column("pre_workout_fuel", sa.Text()),
)


def _split_fuel(text: str) -> list[str]:
    import re

    return [t.strip() for t in re.split(r"[,;]", text) if t.strip()]


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_sessions.c.id, _sessions.c.tags, _sessions.c.pre_workout_fuel).where(
            _sessions.c.pre_workout_fuel.is_not(None)
        )
    ).all()
    for row in rows:
        fuel = (row.pre_workout_fuel or "").strip()
        if not fuel:
            continue
        tags = list(row.tags or [])
        for tag in _split_fuel(fuel):
            if tag not in tags:
                tags.append(tag)
        bind.execute(
            _sessions.update().where(_sessions.c.id == row.id).values(tags=tags)
        )

    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_column("pre_workout_fuel")


def downgrade() -> None:
    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pre_workout_fuel", sa.Text(), nullable=True))
