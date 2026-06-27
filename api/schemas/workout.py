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


class SetUpdate(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool | None = None


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
    rest_seconds: int | None = None
    notes: str | None = None


class SessionExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
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
