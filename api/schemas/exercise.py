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
    is_timed: bool = False
    aliases: list[str] = []


class ExerciseBrief(BaseModel):
    """Lightweight exercise reference embedded in templates / sessions / history."""

    id: int
    name: str
    primary_muscles: list[str] = []
    equipment: str | None = None
    is_timed: bool = False


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
    # 'created' (new row) or 'exact' (blocked: normalized-name match).
    reason: str
    exercise: ExerciseOut | None = None
    duplicate_of: ExerciseOut | None = None
    # Non-blocking "similar exercise" hint, populated alongside a successful
    # create when the name-only index finds a close catalog neighbor. Never
    # gates creation — advisory only.
    similar_to: ExerciseOut | None = None
    similar_to_similarity: float | None = None


class AliasCreate(BaseModel):
    alias_text: str = Field(min_length=1)


class PerformedSet(BaseModel):
    set_number: int
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False


class ExercisePerformance(BaseModel):
    """One past session's sets for an exercise (UI 'previous performance')."""

    session_id: int
    session_name: str | None = None
    date: datetime
    sets: list[PerformedSet]
