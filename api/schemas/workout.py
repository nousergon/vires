"""Workout session / logging schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from api.schemas.exercise import ExerciseBrief, ExercisePerformance


class WorkoutStart(BaseModel):
    template_id: int | None = None  # None => empty/ad-hoc workout
    name: str | None = None


class SetIn(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    set_number: int | None = None  # auto-assigned (next) when omitted
    # Whether the new set is already performed. Defaults True (a directly-logged
    # set). The app passes False from "+ Add set" so an empty row appears unchecked
    # for the user to fill in and tick off themselves.
    done: bool = True


class SetUpdate(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool | None = None
    # Mark the set done/undone — stamps (or clears) completed_at server-side.
    done: bool | None = None


class SetOut(BaseModel):
    id: int
    set_number: int
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    completed_at: datetime | None = None


class SessionExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class SessionExerciseUpdate(BaseModel):
    """Patch a session exercise in place: tweak its rest/targets or reorder it.

    All fields optional; only those present (``exclude_unset``) are applied.
    ``order_index`` drives drag-free reordering (the app swaps adjacent rows).
    """

    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    order_index: int | None = None


class SessionExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[SetOut]
    # Most recent prior performance of this exercise (the "last time" hint).
    previous_performance: ExercisePerformance | None = None


class WorkoutSessionOut(BaseModel):
    id: int
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    notes: str | None = None
    template_id: int | None = None
    exercises: list[SessionExerciseOut]


class WorkoutSummary(BaseModel):
    id: int
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    exercise_count: int
    set_count: int
    total_volume: float = Field(
        default=0.0, description="Sum of reps*weight over completed working sets"
    )
