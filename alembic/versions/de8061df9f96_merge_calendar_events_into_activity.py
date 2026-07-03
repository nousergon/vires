"""merge calendar_events into workout_sessions/activity_details

Revision ID: de8061df9f96
Revises: 52e681744f33
Create Date: 2026-07-02

Retires ``CalendarEvent``/``calendar_events``. There is no more a stored
"planned" vs. "happened" distinction anywhere in the schema — whether an
activity is upcoming or already occurred is derived purely from
``WorkoutSession.started_at``/``ended_at`` vs. "now" at read time (see
``api.routers.plan.calendar``), never a column. This mirrors the merge
``a7ad5d99b363`` already did once (folding ``ruck_details`` into
``activity_details``) — same target table, same "no shortcuts, fold the
whole concept in" approach.

Adds ``sport``/``event_end_date``/``recurrence``/``objective_id`` to
``activity_details`` (the event-only axes that had no prior home there) and
a self-referential ``recurrence_source_id`` to ``workout_sessions`` (links a
materialized weekly occurrence back to the recurring template row it was
expanded from — mirrors ``planned_workout_id``'s "which row this one
fulfilled" pattern one level up).

Every existing ``calendar_events`` row is backfilled into one
``workout_sessions`` (``session_type='activity'``, ``ended_at=NULL`` —
``CalendarEvent`` never had an "actuals" concept, so every migrated row
starts "not yet closed out," exactly like a materialized-but-unfilled
occurrence would) + one ``activity_details`` row, before ``calendar_events``
is dropped. ``calendar_events.type`` has no functional reader outside
display (grounding text for the coach LLM, ``api.services.coach.context``)
— folded into five new ``activity_templates`` catalog entries
(race/league_game/recreation_event/trip/rehab_window) rather than kept as
its own column.

IMPORTANT — this revision id is freshly generated (``secrets.token_hex(6)``),
not copy-pasted. A copy-pasted placeholder id caused a two-head production
outage on 2026-07-01 (vires-ops#39, see ``a7ad5d99b363`` and
``tests/test_alembic_migrations.py``). Do not reuse this id or its pattern
for a future revision.
"""

from datetime import UTC, datetime, time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "de8061df9f96"
down_revision: Union[str, Sequence[str], None] = "52e681744f33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CalendarEvent.type -> the new activity_templates catalog key it folds into
# (api.services.activity_templates). See the ACTIVITY_TEMPLATES update in the
# same PR for the catalog entries themselves.
_TYPE_TO_TEMPLATE_KEY = {
    "competition": "race",
    "league": "league_game",
    "recreation": "recreation_event",
    "travel": "trip",
    "rehab": "rehab_window",
}


def upgrade() -> None:
    # 1. Additive columns.
    with op.batch_alter_table("activity_details", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sport", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("event_end_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("recurrence", sa.String(), nullable=False, server_default="none")
        )
        batch_op.add_column(sa.Column("objective_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_activity_details_objective_id", ["objective_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_activity_details_objective_id",
            "objectives",
            ["objective_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("recurrence_source_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_workout_sessions_recurrence_source_id",
            ["recurrence_source_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_workout_sessions_recurrence_source_id",
            "workout_sessions",
            ["recurrence_source_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2. Data migration: one calendar_events row -> one workout_sessions row +
    #    one activity_details row. Done row-by-row (not a single INSERT...
    #    SELECT, unlike the simpler ruck-merge precedent) because each new
    #    session's autoincrement id must be captured to link its
    #    activity_details row, and load->>regions/intensity/duration_min needs
    #    JSON extraction that's simplest expressed in Python here.
    bind = op.get_bind()
    calendar_events = sa.table(
        "calendar_events",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("sport", sa.String),
        sa.column("type", sa.String),
        sa.column("event_date", sa.Date),
        sa.column("event_end_date", sa.Date),
        sa.column("recurrence", sa.String),
        sa.column("load", sa.JSON),
        sa.column("notes", sa.Text),
        sa.column("objective_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )
    workout_sessions = sa.table(
        "workout_sessions",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("session_type", sa.String),
        sa.column("started_at", sa.DateTime),
        sa.column("ended_at", sa.DateTime),
        sa.column("notes", sa.Text),
    )
    activity_details = sa.table(
        "activity_details",
        sa.column("session_id", sa.Integer),
        sa.column("template_key", sa.String),
        sa.column("regions", sa.String),
        sa.column("intensity", sa.String),
        sa.column("duration_s", sa.Integer),
        sa.column("sport", sa.String),
        sa.column("event_end_date", sa.Date),
        sa.column("recurrence", sa.String),
        sa.column("objective_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )

    rows = bind.execute(sa.select(calendar_events)).mappings().all()
    for r in rows:
        load = r["load"] or {}
        # calendar_events.event_date was a pure Date; pin to midnight UTC
        # (naive, matching how UTCDateTime stores every other timestamp).
        started_at = datetime.combine(r["event_date"], time.min, tzinfo=UTC).replace(tzinfo=None)
        bind.execute(
            workout_sessions.insert().values(
                tenant_id=r["tenant_id"],
                user_id=r["user_id"],
                name=r["name"],
                session_type="activity",
                started_at=started_at,
                ended_at=None,
                notes=r["notes"],
            )
        )
        # `sa.table()` (lowercase, a bare TableClause) carries no primary-key
        # metadata, so `result.inserted_primary_key` is unavailable — SQLite
        # only, per api.config's default database_url, so last_insert_rowid()
        # is a safe, direct way to recover the new session's id.
        session_id = bind.execute(sa.text("SELECT last_insert_rowid()")).scalar_one()
        bind.execute(
            activity_details.insert().values(
                session_id=session_id,
                template_key=_TYPE_TO_TEMPLATE_KEY.get(r["type"], "custom"),
                regions=load.get("regions", "full"),
                intensity=load.get("intensity", "moderate"),
                duration_s=(load["duration_min"] * 60) if load.get("duration_min") else None,
                sport=r["sport"],
                event_end_date=r["event_end_date"],
                recurrence=r["recurrence"],
                objective_id=r["objective_id"],
                created_at=r["created_at"],
            )
        )

    # 3. Drop calendar_events.
    op.drop_index("ix_calendar_events_objective_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_user_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_tenant_id", table_name="calendar_events")
    op.drop_table("calendar_events")


def downgrade() -> None:
    """Best-effort, not a perfect inverse (same caveat as a7ad5d99b363): any
    NEW activity created after the merge that uses recurrence/event_end_date/
    objective_id on an ordinary (non-event) template — e.g. a recurring
    weekly "Hike" — has no CalendarEvent-shaped equivalent and is silently
    NOT restored on downgrade. Recreates calendar_events from
    activity_details rows that look event-shaped (recurrence != 'none' OR
    event_end_date IS NOT NULL OR objective_id IS NOT NULL OR template_key in
    the 5 folded event keys), reversing the template_key -> type map
    (unrecognized event-shaped template_key defaults to 'competition'), then
    drops the added columns. calendar_events.updated_at has no successor
    column (neither workout_sessions nor activity_details tracks
    updated_at) and is NOT restored — a deliberate, minor, low-value data
    loss on downgrade, not a shortcut on the forward migration.
    """
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sport", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_end_date", sa.Date(), nullable=True),
        sa.Column("recurrence", sa.String(), nullable=False, server_default="none"),
        sa.Column("load", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("objective_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["objective_id"], ["objectives.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_calendar_events_tenant_id", "calendar_events", ["tenant_id"])
    op.create_index("ix_calendar_events_user_id", "calendar_events", ["user_id"])
    op.create_index("ix_calendar_events_objective_id", "calendar_events", ["objective_id"])

    bind = op.get_bind()
    workout_sessions = sa.table(
        "workout_sessions",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("session_type", sa.String),
        sa.column("started_at", sa.DateTime),
        sa.column("notes", sa.Text),
    )
    activity_details = sa.table(
        "activity_details",
        sa.column("session_id", sa.Integer),
        sa.column("template_key", sa.String),
        sa.column("regions", sa.String),
        sa.column("intensity", sa.String),
        sa.column("duration_s", sa.Integer),
        sa.column("sport", sa.String),
        sa.column("event_end_date", sa.Date),
        sa.column("recurrence", sa.String),
        sa.column("objective_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )
    calendar_events = sa.table(
        "calendar_events",
        sa.column("tenant_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("sport", sa.String),
        sa.column("type", sa.String),
        sa.column("event_date", sa.Date),
        sa.column("event_end_date", sa.Date),
        sa.column("recurrence", sa.String),
        sa.column("load", sa.JSON),
        sa.column("notes", sa.Text),
        sa.column("objective_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    _TEMPLATE_KEY_TO_TYPE = {v: k for k, v in _TYPE_TO_TEMPLATE_KEY.items()}

    event_shaped = bind.execute(
        sa.select(
            workout_sessions.c.tenant_id,
            workout_sessions.c.user_id,
            workout_sessions.c.name,
            workout_sessions.c.started_at,
            workout_sessions.c.notes,
            activity_details.c.template_key,
            activity_details.c.regions,
            activity_details.c.intensity,
            activity_details.c.duration_s,
            activity_details.c.sport,
            activity_details.c.event_end_date,
            activity_details.c.recurrence,
            activity_details.c.objective_id,
            activity_details.c.created_at,
        )
        .select_from(
            workout_sessions.join(
                activity_details, activity_details.c.session_id == workout_sessions.c.id
            )
        )
        .where(
            sa.or_(
                activity_details.c.recurrence != "none",
                activity_details.c.event_end_date.is_not(None),
                activity_details.c.objective_id.is_not(None),
                activity_details.c.template_key.in_(_TEMPLATE_KEY_TO_TYPE.keys()),
            )
        )
    ).mappings().all()

    for r in event_shaped:
        duration_min = (r["duration_s"] // 60) if r["duration_s"] else None
        load = {"regions": r["regions"], "intensity": r["intensity"], "duration_min": duration_min}
        bind.execute(
            calendar_events.insert().values(
                tenant_id=r["tenant_id"],
                user_id=r["user_id"],
                name=r["name"],
                sport=r["sport"],
                type=_TEMPLATE_KEY_TO_TYPE.get(r["template_key"], "competition"),
                event_date=r["started_at"].date(),
                event_end_date=r["event_end_date"],
                recurrence=r["recurrence"],
                load=load,
                notes=r["notes"],
                objective_id=r["objective_id"],
                created_at=r["created_at"],
                updated_at=r["created_at"],
            )
        )

    with op.batch_alter_table("workout_sessions", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_workout_sessions_recurrence_source_id", type_="foreignkey"
        )
        batch_op.drop_index("ix_workout_sessions_recurrence_source_id")
        batch_op.drop_column("recurrence_source_id")
    with op.batch_alter_table("activity_details", schema=None) as batch_op:
        batch_op.drop_constraint("fk_activity_details_objective_id", type_="foreignkey")
        batch_op.drop_index("ix_activity_details_objective_id")
        batch_op.drop_column("objective_id")
        batch_op.drop_column("recurrence")
        batch_op.drop_column("event_end_date")
        batch_op.drop_column("sport")
