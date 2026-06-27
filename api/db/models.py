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

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
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
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow
    )


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
    # Seam for the deferred AI coach: which program slot generated this session.
    program_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_slots.id"), nullable=True
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
# Deferred AI-coach layer (schema-ready, unused by MVP UI — brief §4.2/§5a)
# Sequences and progresses WorkoutTemplates across weeks.
# --------------------------------------------------------------------------- #
class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    weeks: Mapped[list[ProgramWeek]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="ProgramWeek.week_index",
    )


class ProgramWeek(Base):
    __tablename__ = "program_weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    week_index: Mapped[int] = mapped_column(Integer, default=0)

    program: Mapped[Program] = relationship(back_populates="weeks")
    slots: Mapped[list[ProgramSlot]] = relationship(
        back_populates="week",
        cascade="all, delete-orphan",
        order_by="ProgramSlot.day_index",
    )


class ProgramSlot(Base):
    __tablename__ = "program_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_week_id: Mapped[int] = mapped_column(
        ForeignKey("program_weeks.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_templates.id"), nullable=True
    )
    day_index: Mapped[int] = mapped_column(Integer, default=0)
    progression_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    week: Mapped[ProgramWeek] = relationship(back_populates="slots")
