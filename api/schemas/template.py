"""Workout template ("Routine") schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from api.schemas.exercise import ExerciseBrief


class SwapFeedbackOut(BaseModel):
    """Equivalence judgment for one exercise substitution detected on a
    template update — see api.services.exercise_swap.evaluate_swap."""

    from_exercise: ExerciseBrief
    to_exercise: ExerciseBrief
    verdict: str  # equivalent | comparable | different_stimulus
    same_pattern: bool
    muscle_overlap: float
    equipment_changed: bool
    rationale: str


class TemplateExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class TemplateExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1)
    notes: str | None = None
    exercises: list[TemplateExerciseIn] = []


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    notes: str | None = None
    # When provided, fully replaces the template's exercise list (order = list order).
    exercises: list[TemplateExerciseIn] | None = None


class TemplateOut(BaseModel):
    id: int
    name: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    exercises: list[TemplateExerciseOut]
    # Populated on PUT /templates/{id} when the exercise list changed —
    # one entry per detected substitution (not present on GET/POST).
    swap_feedback: list[SwapFeedbackOut] = []


class TemplateSummary(BaseModel):
    id: int
    name: str
    notes: str | None = None
    exercise_count: int
    updated_at: datetime
