"""Workout template ("Routine") schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from api.schemas.exercise import ExerciseBrief


class TemplateExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class TemplateExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
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


class TemplateSummary(BaseModel):
    id: int
    name: str
    notes: str | None = None
    exercise_count: int
    updated_at: datetime
