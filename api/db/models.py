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
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which routine this session was started from (nullable => empty/ad-hoc workout).
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_templates.id"), nullable=True
    )
    # Which planned (AI-coach or manually-scheduled) workout this session fulfilled.
    planned_workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("planned_workouts.id"), nullable=True
    )

    exercises: Mapped[list[SessionExercise]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionExercise.order_index",
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

    session_exercise: Mapped[SessionExercise] = relationship(back_populates="sets")


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
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
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
    # The peak/summit day. A pure Date (a goal belongs to a *day*), nullable for
    # open-ended objectives; required for dated ones (enforced in the schema).
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Sport profile key — 'alpine' is the only authored needs-analysis for now.
    sport: Mapped[str | None] = mapped_column(String, nullable=True)
    # The needs-analysis the coach consumes (structured JSON; see
    # api.services.coach.objective_profiles). This is the data that makes the
    # coach credible rather than generic.
    demands_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
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
