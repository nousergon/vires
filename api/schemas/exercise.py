"""Exercise request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExerciseOut(BaseModel):
    id: int
    name: str
    primary_muscles: list[str] = []
    secondary_muscles: list[str] = []
    equipment: str | None = None
    mechanic: str | None = None
    category: str | None = None
    description: str | None = None
    provenance: str
    aliases: list[str] = []


class ExerciseBrief(BaseModel):
    """Lightweight exercise reference embedded in templates / sessions / history."""

    id: int
    name: str
    primary_muscles: list[str] = []
    equipment: str | None = None


class ExerciseSearchOut(BaseModel):
    exercise: ExerciseOut
    score: float


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1)
    primary_muscles: list[str] = []
    secondary_muscles: list[str] = []
    equipment: str | None = None
    mechanic: str | None = None
    category: str | None = None
    description: str | None = None
    # Skip dedup and create regardless of near-duplicates.
    force: bool = False


class ExerciseCreateResult(BaseModel):
    created: bool
    # 'created' (new row), 'exact' (normalized-name match), 'similar' (advisory)
    reason: str
    exercise: ExerciseOut | None = None
    duplicate_of: ExerciseOut | None = None
    similarity: float | None = None


class AliasCreate(BaseModel):
    alias_text: str = Field(min_length=1)


class PerformedSet(BaseModel):
    set_number: int
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    is_warmup: bool = False


class ExercisePerformance(BaseModel):
    """One past session's sets for an exercise (UI 'previous performance')."""

    session_id: int
    session_name: str | None = None
    date: datetime
    sets: list[PerformedSet]
