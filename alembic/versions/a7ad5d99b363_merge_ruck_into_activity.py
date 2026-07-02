"""merge ruck_details into activity_details

Revision ID: a7ad5d99b363
Revises: c3d4e5f6a7b8
Create Date: 2026-07-02

Retires ``session_type == 'ruck'`` and the ``ruck_details`` table. Pack
weight + bodyweight + route detail become optional columns on
``activity_details`` instead of a separate physics-modeled type — a light
pack on a Walk/Run is exactly as real as a heavy pack on a Hike, and users
who don't care about the load estimate shouldn't be forced to enter one. See
``api.db.models.ActivityDetail`` docstring for the full rationale.

IMPORTANT — this revision id is freshly generated (``secrets.token_hex(6)``),
not copy-pasted from another revision. A copy-pasted placeholder id on this
exact ruck/calendar migration pair caused a two-head production outage on
2026-07-01 (vires-ops#39, ~2hr of failed deploys — see
``tests/test_alembic_migrations.py``). Do not reuse this id or its pattern
for a future revision.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7ad5d99b363"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Additive columns — nullable, so existing activity_details rows are
    #    unaffected.
    with op.batch_alter_table("activity_details", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pack_weight_kg", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("bodyweight_kg", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("distance_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("elevation_gain_m", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("terrain", sa.String(), nullable=False, server_default="trail")
        )
        batch_op.add_column(sa.Column("metabolic_cost_kj", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("source", sa.String(), nullable=False, server_default="manual")
        )

    # 2. Backfill every ruck_details row into activity_details. ruck_details
    #    never tracked regions/intensity (that vocabulary didn't exist for
    #    rucks), so this is a judgment call: 'legs' (a ruck is a lower-body /
    #    weight-bearing carry) and 'moderate' (heavier than the unloaded
    #    "Hiking" catalog entry it replaces, since every ruck carried a
    #    mandatory pack). template_key='hike' — a ruck IS a loaded hike under
    #    the merged vocabulary.
    op.execute(
        sa.text(
            """
            INSERT INTO activity_details
                (session_id, template_key, duration_s, regions, intensity,
                 pack_weight_kg, bodyweight_kg, distance_m, elevation_gain_m,
                 terrain, metabolic_cost_kj, source, created_at)
            SELECT session_id, 'hike', duration_s, 'legs', 'moderate',
                   pack_weight_kg, bodyweight_kg, distance_m, elevation_gain_m,
                   terrain, metabolic_cost_kj, source, created_at
            FROM ruck_details
            """
        )
    )

    # 3. Every migrated session is now a plain 'activity' session.
    op.execute(
        sa.text("UPDATE workout_sessions SET session_type = 'activity' "
                "WHERE session_type = 'ruck'")
    )

    # 4. Drop the now-empty-of-purpose ruck_details table.
    op.drop_index(op.f("ix_ruck_details_session_id"), table_name="ruck_details")
    op.drop_table("ruck_details")


def downgrade() -> None:
    # NOTE: best-effort, not a perfect inverse. Once pack weight is legal on
    # any template (the whole point of this merge), there is no remaining
    # discriminator between "a ruck" and "a pack-loaded walk/run" — any
    # activity logged AFTER the upgrade that happens to carry both a pack
    # weight and a bodyweight gets reclassified back to 'ruck' on downgrade,
    # even if the user picked "Walk" or "Run", not "Hike". This is an
    # unavoidable consequence of a genuine concept merge (not a shortcut — a
    # perfectly reversible round-trip would require keeping a field we're
    # deliberately deleting). Downgrade exists for rolling back the schema
    # change itself in the window before real post-merge data accumulates,
    # not as a long-term reversible toggle.
    op.create_table(
        "ruck_details",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("pack_weight_kg", sa.Float(), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("terrain", sa.String(), nullable=False, server_default="trail"),
        sa.Column("metabolic_cost_kj", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["workout_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_ruck_details_session_id"), "ruck_details", ["session_id"], unique=False
    )

    op.execute(
        sa.text(
            """
            INSERT INTO ruck_details
                (session_id, pack_weight_kg, bodyweight_kg, distance_m,
                 elevation_gain_m, duration_s, terrain, metabolic_cost_kj,
                 source, created_at)
            SELECT session_id, pack_weight_kg, bodyweight_kg, distance_m,
                   elevation_gain_m, duration_s, terrain, metabolic_cost_kj,
                   source, created_at
            FROM activity_details
            WHERE pack_weight_kg IS NOT NULL AND bodyweight_kg IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            "UPDATE workout_sessions SET session_type = 'ruck' "
            "WHERE id IN (SELECT session_id FROM ruck_details)"
        )
    )

    with op.batch_alter_table("activity_details", schema=None) as batch_op:
        batch_op.drop_column("source")
        batch_op.drop_column("metabolic_cost_kj")
        batch_op.drop_column("terrain")
        batch_op.drop_column("elevation_gain_m")
        batch_op.drop_column("distance_m")
        batch_op.drop_column("bodyweight_kg")
        batch_op.drop_column("pack_weight_kg")
