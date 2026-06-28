"""Calendar / planned-workout schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from api.schemas.exercise import ExerciseBrief


class CalendarEntry(BaseModel):
    """One dot on the calendar — a past session or a future planned workout."""

    kind: str  # 'session' | 'planned'
    date: date
    id: int
    name: str | None = None
    # session: 'completed' | 'in_progress'; planned: 'planned' | 'completed' | 'skipped'
    status: str
    program_id: int | None = None
    template_id: int | None = None
    exercise_count: int = 0
    session_id: int | None = None  # planned -> the session that fulfilled it, if any


class PlannedExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class PlannedExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class PlannedWorkoutOut(BaseModel):
    id: int
    program_id: int | None = None
    template_id: int | None = None
    scheduled_date: date
    name: str
    notes: str | None = None
    week_index: int | None = None
    status: str
    created_by: str
    session_id: int | None = None
    exercises: list[PlannedExerciseOut]


class PlannedWorkoutUpdate(BaseModel):
    scheduled_date: date | None = None
    name: str | None = Field(default=None, min_length=1)
    notes: str | None = None
    status: str | None = None  # planned | completed | skipped
    # When provided, fully replaces the prescription (order = list order).
    exercises: list[PlannedExerciseIn] | None = None


class PlannedWorkoutCreate(BaseModel):
    """Manually schedule a single workout (no coach) from a template or empty."""

    scheduled_date: date
    template_id: int | None = None
    name: str | None = None
    notes: str | None = None


class ProgramSummary(BaseModel):
    id: int
    name: str
    goal_text: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str
    planned_count: int
    completed_count: int


class ProgramOut(BaseModel):
    id: int
    name: str
    notes: str | None = None
    goal_text: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str
    created_at: datetime
    planned_workouts: list[PlannedWorkoutOut]
