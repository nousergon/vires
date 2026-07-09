"""SQLAlchemy ORM models.

Design notes
------------
* **Multitenancy-ready, single-user now.** Every user-owned row carries
  ``tenant_id`` + ``user_id``. The MVP runs as one hardcoded dev identity
  (see ``api.config``); enabling auth later is a flip, not a migration.
* **Program is first-class from day one** (brief §4.2). The user-built
  ``WorkoutTemplate`` (Strong "Routine") is the reusable unit; the deferred
  AI coach layer (``Program`` → ``ProgramWeek`` → ``ProgramSlot``) *sequences
  and progresses templates across weeks* rather than inventing a parallel
  structure. The program tables exist now but are unused by the MVP UI.
* **Exercise catalog** mixes global canonical entries (``tenant_id IS NULL``)
  with user/provisional additions. Near-duplicates collapse to a canonical via
  ``canonical_exercise_id`` + ``ExerciseAlias`` (embedding dedup, brief §5c).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.db.types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Identity (schema-ready multitenancy)
# --------------------------------------------------------------------------- #
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)


class UserSettings(Base):
    """Per-user preferences (one row per user). Drives logging defaults + units."""

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    weight_unit: Mapped[str] = mapped_column(String, default="lb")  # 'lb' | 'kg'
    default_rest_seconds: Mapped[int] = mapped_column(Integer, default=90)
    default_sets: Mapped[int] = mapped_column(Integer, default=3)
    default_reps: Mapped[int] = mapped_column(Integer, default=8)
    # Unguessable token for the public (unauthenticated) ICS calendar feed —
    # Google/Apple Calendar fetch the feed anonymously, so the token IS the auth.
    # Lazily minted on first feed-url access; rotatable.
    feed_token: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    # Timer-end alert preferences (rest + hold timers). Notification defaults off
    # since it needs per-device permission; keep-awake on (high-value, screen
    # stays on so the sound/visual reliably fire mid-rest).
    timer_sound: Mapped[bool] = mapped_column(Boolean, default=True)
    timer_vibration: Mapped[bool] = mapped_column(Boolean, default=True)
    timer_notification: Mapped[bool] = mapped_column(Boolean, default=False)
    timer_keep_awake: Mapped[bool] = mapped_column(Boolean, default=True)
    # Durable weekly-lifting day preference (e.g. ["monday", "thursday"]) — set
    # once here so the coach honors it on every generation without the user
    # re-stating it in each conversation. Empty = no standing preference, let
    # the coach/user's message pick the day(s) as before.
    preferred_weekdays: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )


class PushSubscription(Base):
    """A browser Web Push subscription (one per device that opted in). The
    ``endpoint`` is the push service URL; ``p256dh``/``auth`` are the client's
    encryption keys. Used to deliver locked-screen timer alerts."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)


# --------------------------------------------------------------------------- #
# Exercise catalog
# --------------------------------------------------------------------------- #
class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NULL tenant_id => global canonical entry shared by all tenants.
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    primary_muscles: Mapped[list] = mapped_column(JSON, default=list)
    secondary_muscles: Mapped[list] = mapped_column(JSON, default=list)
    equipment: Mapped[str | None] = mapped_column(String, nullable=True)
    mechanic: Mapped[str | None] = mapped_column(String, nullable=True)  # compound/isolation
    category: Mapped[str | None] = mapped_column(String, nullable=True)  # strength/cardio/...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'canonical' (curated), 'provisional' (model/user-created, unverified), 'user'
    provenance: Mapped[str] = mapped_column(String, default="provisional", index=True)
    # Isometric/hold movement (plank, stretches): logged by duration, not reps.
    # Seeded from free-exercise-db force=="static".
    is_timed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Alias pointer: when set, this row is a synonym of the referenced canonical exercise.
    canonical_exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    aliases: Mapped[list[ExerciseAlias]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        foreign_keys="ExerciseAlias.exercise_id",
    )


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    alias_text: Mapped[str] = mapped_column(String, nullable=False)

    exercise: Mapped[Exercise] = relationship(
        back_populates="aliases", foreign_keys=[exercise_id]
    )


# --------------------------------------------------------------------------- #
# Templates / Routines (active MVP feature — Strong "Routines")
# --------------------------------------------------------------------------- #
class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    exercises: Mapped[list[TemplateExercise]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateExercise.order_index",
    )


class TemplateExercise(Base):
    __tablename__ = "template_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Placeholder starting weight (user-set; the AI coach will propose it later).
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Target hold duration (seconds) for timed exercises (e.g. plank).
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped[WorkoutTemplate] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


# --------------------------------------------------------------------------- #
# Logged execution (what the MVP writes)
# --------------------------------------------------------------------------- #
class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Discriminator for the kind of training this session records. 'strength' is
    # the reps/weight/exercises MVP; 'activity' is everything else — generic
    # cross-training (climbing, swimming, yoga, ...) AND locomotion activities
    # (walk/run/hike, optionally loaded with a pack) — whose coarse load and
    # optional route/load-carriage detail lives 1:1 in ``activity_details``.
    # Kept as a plain column (single history/calendar/objective spine) rather
    # than a parallel table, so any session type flows through the same session
    # machinery as a lift.
    session_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default="strength", default="strength"
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text labels for the session — a mix of reusable tags ("push day",
    # "fasted") and one-off custom inputs. Stored as a JSON list of strings so a
    # user can coin a new tag inline without a lookup table. Empty list => none.
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # What was eaten/drunk/supplemented before training (food, drink, caffeine,
    # creatine, ...). Free text — kept as one field rather than a structured
    # intake log, which is out of scope for this tracker.
    pre_workout_fuel: Mapped[str | None] = mapped_column(Text, nullable=True)
    # End-of-workout self-report on a 1–10 scale, prompted when the session is
    # finished. ``energy_level`` = how the body felt (readiness);
    # ``workout_intensity`` = how hard the session was (RPE-like, whole-session).
    # Named ``workout_intensity`` (not ``intensity``) to stay distinct from the
    # activity load's coarse ``intensity`` (light/moderate/hard) on the 1:1
    # ``ActivityDetail`` row. Both nullable — a session finished before the
    # prompt existed, or dismissed, simply has none.
    energy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workout_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which routine this session was started from (nullable => empty/ad-hoc workout).
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_templates.id"), nullable=True
    )
    # Which planned (AI-coach or manually-scheduled) workout this session fulfilled.
    planned_workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("planned_workouts.id"), nullable=True
    )
    # Set ONLY on a materialized occurrence of a recurring activity (see
    # ActivityDetail.recurrence) — points back at the recurring "template"
    # session it was expanded from. None on the template row itself and on
    # every non-recurring session. Mirrors planned_workout_id's "which row
    # this one fulfilled" linkage, one level up (series -> instance instead
    # of plan -> instance).
    recurrence_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    exercises: Mapped[list[SessionExercise]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionExercise.order_index",
    )
    # Type-specific detail for a non-strength session; None for strength.
    activity_detail: Mapped[ActivityDetail | None] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SessionExercise(Base):
    __tablename__ = "session_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[WorkoutSession] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()
    sets: Mapped[list[SetEntry]] = relationship(
        back_populates="session_exercise",
        cascade="all, delete-orphan",
        order_by="SetEntry.set_number",
    )


class SetEntry(Base):
    __tablename__ = "set_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("session_exercises.id", ondelete="CASCADE"), index=True
    )
    set_number: Mapped[int] = mapped_column(Integer, default=1)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_warmup: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    # Client-generated UUID for an offline-first set log (vires-ops#48). The PWA
    # mints this with crypto.randomUUID() BEFORE the POST, so a write queued in
    # IndexedDB while offline carries a stable identity across replays. The
    # unique index below makes replay idempotent: re-POSTing the same UUID under
    # the same exercise returns the existing row instead of appending a
    # duplicate (append-wins on a client-supplied identity — the groomer's
    # settled conflict semantics for this append-only set log). Nullable: online
    # writes and every pre-existing row have no client UUID.
    client_uuid: Mapped[str | None] = mapped_column(String(), nullable=True)

    session_exercise: Mapped[SessionExercise] = relationship(back_populates="sets")

    __table_args__ = (
        UniqueConstraint(
            "session_exercise_id",
            "client_uuid",
            name="uq_set_entries_se_client_uuid",
        ),
    )


class ActivityDetail(Base):
    """Non-strength session detail — 1:1 with a ``WorkoutSession`` whose
    ``session_type == 'activity'``. Covers both generic cross-training
    (climbing, swimming, yoga, ...) and locomotion activities (walk/run/hike),
    which may optionally carry a weighted pack.

    **Why generic rather than a bespoke type per activity:** a dedicated table
    per sport doesn't scale, and most cross-training has no domain-specific
    physics model worth the schema cost. Every activity — from a template or
    freeform — reduces to the same coarse load shape already established for
    athletic-calendar events (``CalendarEvent.load``, vires-ops#33): which body
    regions it taxes and how hard. Reusing that vocabulary (rather than
    inventing a parallel one) means the coach's existing recovery-budget
    reasoning generalizes to logged activities for free — see
    ``api.services.coach.context``.

    **Route + load-carriage fields are optional on every template**, not a
    separate physics-modeled type. Originally a "ruck" (loaded hike) was its
    own ``session_type``/table with a mandatory pack weight; that distinction
    didn't hold up — a light pack on a Walk or Run is exactly as physiologically
    real as a heavy pack on a Hike, and users who don't care about the load
    number shouldn't be forced to enter one. So ``pack_weight_kg`` /
    ``bodyweight_kg`` / ``distance_m`` / ``elevation_gain_m`` / ``terrain`` /
    ``metabolic_cost_kj`` / ``source`` now live here as nullable columns,
    populated whenever a route-capable template (walk/run/hike — see
    ``api.services.activity_templates``) is logged with that data. Merged from
    the former ``ruck_details`` table (see the ``merge_ruck_into_activity``
    migration) — units for the carried-over fields stay canonical SI with
    explicit suffixes (``_kg`` / ``_m`` / ``_s``), matching the Pandolf load
    model's units and the GPX/route-import paths, which deliver SI natively.
    Conversion to/from the user's display unit happens once, at the API
    boundary — never here.

    **Also covers what used to be the separate ``CalendarEvent`` table**
    (races, league games, trips, rehab windows — merged
    ``merge_calendar_events_into_activity`` migration). There is no stored
    "planned" vs. "happened" distinction anywhere in this schema: whether a
    row is upcoming or already occurred is derived purely from
    ``WorkoutSession.started_at``/``ended_at`` vs. "now" at read time (see
    ``api.routers.plan.calendar``'s status derivation) — never a column
    here. ``sport``/``event_end_date``/``recurrence``/``objective_id`` are
    the event-only axes that had no prior home on this table; a "weekly"
    recurring row is never itself closed out (``ended_at`` stays ``None``)
    — its concrete occurrences are expanded on read (see
    ``api.services.recurrence.expand_occurrences``) and only materialize
    into their own linked row (``WorkoutSession.recurrence_source_id``)
    when a user opens one to log what happened.
    """

    __tablename__ = "activity_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Template slug (e.g. 'climbing_indoor_toprope', 'hike') or 'custom' for
    # freeform entry. Display name is ``WorkoutSession.name``, not duplicated here.
    template_key: Mapped[str] = mapped_column(String, nullable=False, default="custom")
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Coarse structured load — same vocabulary as CalendarEvent.load:
    # regions in {'legs','upper','full','core','none'}, intensity in
    # {'light','moderate','hard'}. Template-prefilled, always user-editable.
    regions: Mapped[str] = mapped_column(String, nullable=False, default="full")
    intensity: Mapped[str] = mapped_column(String, nullable=False, default="moderate")
    # Optional load-carriage — set only when the user weighs in a pack for a
    # route-capable template. None means "no load estimate wanted"; it does NOT
    # imply "unloaded" (an unloaded hike and a climbing session are equally
    # None here — that distinction lives in the template's route_capable flag,
    # a frontend/catalog concern, not a schema one).
    pack_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Body mass at time of the activity — required alongside pack_weight_kg to
    # run the Pandolf metabolic-cost model (enforced in ActivityLogIn, not
    # here: the DB stays permissive).
    bodyweight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Coarse terrain class → Pandolf terrain factor η (see api.services.load.pandolf).
    terrain: Mapped[str] = mapped_column(
        String, nullable=False, server_default="trail", default="trail"
    )
    # Pandolf-derived total metabolic cost of the carry (kJ). None whenever
    # pack_weight_kg is None, or when it's set but distance/duration are
    # absent — an honest "not enough input to compute", never fabricated.
    metabolic_cost_kj: Mapped[float | None] = mapped_column(Float, nullable=True)
    # How distance/elevation arrived: 'manual' | 'route_search' | 'route_draw' |
    # 'gpx'. Meaningful for any route-capable template, not just a loaded one.
    source: Mapped[str] = mapped_column(
        String, nullable=False, server_default="manual", default="manual"
    )
    # Sport profile key — reuses the SAME free-text vocabulary as
    # Objective.sport (e.g. 'alpine'); not redefined here. Mainly relevant
    # for event-shaped activities (a race, a league game).
    sport: Mapped[str | None] = mapped_column(String, nullable=True)
    # Last day of a multi-day activity (nullable; e.g. a ski trip). None =>
    # a single-day activity at started_at's date. Not used for a recurring
    # ('weekly') row — recurrence is the multi-occurrence axis there.
    event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # none | weekly. 'weekly' repeats every 7 days from the session's own
    # started_at date, expanded server-side on read within the queried
    # window — never persisted as extra rows (see api.services.recurrence).
    recurrence: Mapped[str] = mapped_column(
        String, nullable=False, server_default="none", default="none"
    )
    # Anchor to an Objective when this activity IS itself a peak target
    # (e.g. the race). Nullable — most activities have none. SET NULL on
    # objective delete so the activity survives as a standalone constraint.
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    session: Mapped[WorkoutSession] = relationship(back_populates="activity_detail")


# --------------------------------------------------------------------------- #
# AI-coach layer — date-bearing program + calendar (brief §4.2/§5a)
#
# A ``Program`` is the coach's output: a named multi-week plan whose declarative
# ``spec`` (the validated ``ProgramSpec``) is materialized deterministically into
# concrete dated ``PlannedWorkout`` rows. The calendar's "future" is the set of
# ``PlannedWorkout``s (by ``scheduled_date``); the "past" is ``WorkoutSession``s
# (by ``started_at``). Starting a planned workout creates a session linked back
# via ``WorkoutSession.planned_workout_id``.
#
# (Replaces the earlier unused relative-grid Program→Week→Slot seam, which had no
# absolute dates and so couldn't drive a calendar — see git history.)
# --------------------------------------------------------------------------- #
class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The objective this plan was built to train for (the coach's strategy lives
    # in ``spec.coach_summary``). Nullable: a plan can be generated without an
    # objective; SET NULL on objective delete so the plan + its history survive.
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The natural-language request the user gave the coach (for display / refine).
    goal_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The validated ProgramSpec the coach produced — kept so the plan can be
    # explained, refined, or re-materialized later.
    spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", index=True)  # active|archived
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    planned_workouts: Mapped[list[PlannedWorkout]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="PlannedWorkout.scheduled_date",
    )


class PlannedWorkout(Base):
    """A workout scheduled on a specific calendar day — the calendar's future unit.

    ``scheduled_date`` is a pure ``Date`` (a plan belongs to a *day*, not an
    instant), which also sidesteps the SQLite tz-stripping pitfall that
    ``UTCDateTime`` exists to solve. ``program_id`` is nullable so a one-off day
    can be scheduled without a coach program.
    """

    __tablename__ = "planned_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Which routine this day was derived from (provenance / "start from template").
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_templates.id"), nullable=True
    )
    # Which objective's training block this day belongs to (the season phase it
    # prepares for). SET NULL so the day survives the objective being deleted.
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Set (to the PRIOR scheduled_date) when api.services.reschedule auto-moves
    # this day forward because it was missed — lets the UI say "moved from Thu
    # 7/2". Never cleared; overwritten with the most recent prior date if moved
    # more than once. None for a day that has never been auto-rescheduled.
    rescheduled_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # display grouping
    status: Mapped[str] = mapped_column(
        String, default="planned", index=True
    )  # planned|completed|skipped
    created_by: Mapped[str] = mapped_column(String, default="coach")  # coach|user
    # The session that fulfilled this planned day (set when the user starts it).
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_sessions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    program: Mapped[Program | None] = relationship(back_populates="planned_workouts")
    exercises: Mapped[list[PlannedExercise]] = relationship(
        back_populates="planned_workout",
        cascade="all, delete-orphan",
        order_by="PlannedExercise.order_index",
    )


class PlannedExercise(Base):
    """The concrete prescription for one exercise on one planned day.

    Mirrors ``TemplateExercise`` / ``SessionExercise``; this is where the coach's
    progression curve is materialized into a specific sets×reps×weight target.
    """

    __tablename__ = "planned_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    planned_workout_id: Mapped[int] = mapped_column(
        ForeignKey("planned_workouts.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    planned_workout: Mapped[PlannedWorkout] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


# --------------------------------------------------------------------------- #
# Objective-driven coaching — the goal the program peaks toward + the
# constraints it must train *around* (build spec: objective-driven coach).
#
# An ``Objective`` is a first-class goal (e.g. "Climb Baker") that anchors the
# coach's periodization: generation reverse-builds a mesocycle that peaks/tapers
# to ``target_date``. A ``Constraint`` (e.g. a recovering disc) is NOT a goal —
# it bounds every objective; the coach trains around it and never prescribes to
# treat it. Both are user-owned (multitenancy-ready like every other row).
# --------------------------------------------------------------------------- #
class Objective(Base):
    """A training goal the coach periodizes toward.

    Exactly one objective per user may be the active *primary* — enforced both
    in the write path (setting one demotes the others) and by a partial unique
    index. Only ``kind='dated'`` (with a ``target_date``) drives the P0 peak/
    taper periodization; ``open_ended`` is stored but not yet date-anchored.
    """

    __tablename__ = "objectives"
    __table_args__ = (
        # At most one primary objective per (tenant, user). Partial unique index
        # is the structural guarantee behind the app-level demote-on-set logic.
        Index(
            "uq_one_primary_objective_per_user",
            "tenant_id",
            "user_id",
            unique=True,
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 'dated' (peaks to target_date) | 'open_ended' (no fixed peak — stored, not
    # yet periodized).
    kind: Mapped[str] = mapped_column(String, nullable=False, default="dated")
    # The peak/summit day — the day you must be READY. A pure Date (a goal belongs
    # to a *day*), nullable for open-ended objectives; required for dated ones.
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Last day of a multi-day event (e.g. a trip). When set, the objective spans
    # target_date..event_end_date with NO training scheduled, and the next block
    # starts after it. None => a single-day event at target_date.
    event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Sport profile key — 'alpine' is the only authored needs-analysis for now.
    sport: Mapped[str | None] = mapped_column(String, nullable=True)
    # The needs-analysis the coach consumes (structured JSON; see
    # api.services.coach.objective_profiles). This is the data that makes the
    # coach credible rather than generic.
    demands_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Manual override pin: at most one per user (partial unique index above). When
    # set it forces the focus; otherwise focus is derived from dates + priority.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Rank among concurrent objectives (higher = more important). Tiebreak when
    # two dated objectives peak on the same day; ordering key for open-ended ones.
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Parent objective this is a *sub-objective* (training milestone) of. When set,
    # the row is a dated benchmark inside the parent's block — NOT a focus-eligible
    # peak of its own (see api.services.objective_focus): it never hijacks the
    # focus, the coach periodizes a mini-taper/retest around it, and completing it
    # counts as training credit toward the parent. SET NULL so deleting the parent
    # leaves the milestone as a standalone objective rather than destroying history.
    # Nesting is one level deep — a sub-objective may not itself be a parent
    # (enforced in the write path).
    parent_objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    # Sub-objectives nested under this one (the parent's training milestones).
    # ``remote_side`` disambiguates the self-referential join; no cascade — a
    # parent delete nulls the FK (SET NULL above) rather than removing children.
    children: Mapped[list[Objective]] = relationship(
        back_populates="parent",
        foreign_keys=lambda: [Objective.parent_objective_id],
    )
    parent: Mapped[Objective | None] = relationship(
        back_populates="children",
        remote_side=lambda: [Objective.id],
        foreign_keys=lambda: [Objective.parent_objective_id],
    )


class Constraint(Base):
    """A bound on training (injury / schedule / equipment) the coach trains around.

    Constraints are NOT goals. For an ``injury`` constraint the coach excludes
    aggravating patterns and biases toward safe supporting work, but NEVER
    prescribes loading/rehab to treat the condition (``defer_to_professional``).
    """

    __tablename__ = "training_constraints"  # 'constraints' brushes a SQL keyword

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # injury|schedule|equipment
    label: Mapped[str] = mapped_column(String, nullable=False)
    # What to avoid / bias toward — text the coach must honor.
    directives: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True for injuries: the coach defers treatment/rehab to a professional.
    defer_to_professional: Mapped[bool] = mapped_column(Boolean, default=False)
    # Active constraints bound generation; deactivate (vs delete) to keep history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )


# --------------------------------------------------------------------------- #
# Ailment episodes — date-anchored injuries the coach adapts around over time.
#
# Unlike static ``Constraint`` rows (schedule/equipment/chronic bounds), an
# ``AilmentEpisode`` tracks onset, severity trajectory via ``AilmentCheckIn``,
# and resolution. The coach consumes the latest check-in + recent trend.
# --------------------------------------------------------------------------- #
class AilmentEpisode(Base):
    __tablename__ = "ailment_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    onset_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # active | improving | resolved
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    resolved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )

    check_ins: Mapped[list[AilmentCheckIn]] = relationship(
        back_populates="ailment",
        cascade="all, delete-orphan",
        order_by="AilmentCheckIn.check_in_date.desc()",
    )


class AilmentCheckIn(Base):
    __tablename__ = "ailment_check_ins"
    __table_args__ = (
        Index(
            "uq_ailment_check_in_per_day",
            "ailment_id",
            "check_in_date",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ailment_id: Mapped[int] = mapped_column(
        ForeignKey("ailment_episodes.id", ondelete="CASCADE"), index=True
    )
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 0 = none, 10 = worst — self-reported discomfort/pain.
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    ailment: Mapped[AilmentEpisode] = relationship(back_populates="check_ins")


# --------------------------------------------------------------------------- #
# Plan-change audit — "why did my plan change?"
#
# Both adaptation loops mutate future planned workouts: the deterministic micro
# loop (autoregulation, per-workout load nudges) and the macro loop (a full
# re-plan / revision applied from the coach). Each writes one row here so the
# change is explainable and the "based on history" behavior is observable.
# --------------------------------------------------------------------------- #
class PlanChangeEvent(Base):
    __tablename__ = "plan_change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # The plan that changed. SET NULL (not CASCADE) so the audit trail outlives a
    # deleted program.
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The session that triggered an autoregulation change (NULL for macro revisions).
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)  # autoregulation|plan_revision
    # What prompted it: autoreg verdict mix, or the re-plan trigger kind(s).
    trigger: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)  # human-readable
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # structured payload
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, index=True)
