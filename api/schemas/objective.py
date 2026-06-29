"""Objective + Constraint schemas (objective-driven coach).

An ``Objective`` is the goal the coach periodizes toward; a ``Constraint`` is a
bound it trains *around* (never a goal). ``demands_profile`` is free-form
structured JSON (the sport needs-analysis the coach consumes — see
``api.services.coach.objective_profiles``); it is intentionally untyped here so
new profile shapes don't require a schema change.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ObjectiveKind = Literal["dated", "open_ended"]
ConstraintKind = Literal["injury", "schedule", "equipment"]


# --------------------------------------------------------------------------- #
# Objective
# --------------------------------------------------------------------------- #
class ObjectiveCreate(BaseModel):
    name: str = Field(min_length=1)
    kind: ObjectiveKind = "dated"
    target_date: date | None = None
    # Last day of a multi-day event (>= target_date); omit for a single-day event.
    event_end_date: date | None = None
    sport: str | None = None
    # Omit to auto-fill from the authored profile for ``sport`` (if one exists).
    demands_profile: dict[str, Any] | None = None
    is_primary: bool = False
    # Rank among concurrent objectives (higher = more important).
    priority: int = 0

    @model_validator(mode="after")
    def _validate_dates(self) -> ObjectiveCreate:
        if self.kind == "dated" and self.target_date is None:
            raise ValueError("target_date is required when kind='dated'")
        if self.event_end_date is not None:
            if self.target_date is None:
                raise ValueError("event_end_date requires target_date")
            if self.event_end_date < self.target_date:
                raise ValueError("event_end_date must be on or after target_date")
        return self


class ObjectiveUpdate(BaseModel):
    """Partial update. Cross-field (dated ⇒ target_date) is validated in the
    router against the merged row, since any field may be absent here."""

    name: str | None = Field(default=None, min_length=1)
    kind: ObjectiveKind | None = None
    target_date: date | None = None
    event_end_date: date | None = None
    sport: str | None = None
    demands_profile: dict[str, Any] | None = None
    is_primary: bool | None = None
    priority: int | None = None


class ObjectiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    target_date: date | None
    event_end_date: date | None
    sport: str | None
    demands_profile: dict[str, Any] | None
    is_primary: bool
    priority: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Constraint
# --------------------------------------------------------------------------- #
class ConstraintCreate(BaseModel):
    kind: ConstraintKind
    label: str = Field(min_length=1)
    directives: str | None = None
    # Omit to default by kind: injuries defer to a professional, others don't.
    defer_to_professional: bool | None = None
    is_active: bool = True


class ConstraintUpdate(BaseModel):
    kind: ConstraintKind | None = None
    label: str | None = Field(default=None, min_length=1)
    directives: str | None = None
    defer_to_professional: bool | None = None
    is_active: bool | None = None


class ConstraintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    label: str
    directives: str | None
    defer_to_professional: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Active context (drives the coach + the frontend banner)
# --------------------------------------------------------------------------- #
class ProgramStrategy(BaseModel):
    """The active plan trained toward the objective + the coach's strategy."""

    program_id: int
    name: str
    coach_summary: str | None


class ActiveObjectiveOut(BaseModel):
    """The active *focus* objective (if any) + the active constraints — the
    context objective-driven generation runs against — plus the active plan's
    strategy, when one has been generated for this objective.

    ``objective`` is the derived focus (next peak / manual pin / standing goal);
    ``objectives`` is the full set the user holds, with dated peaks in
    chronological order first, for the multi-objective timeline UI. The single
    ``objective`` field is retained for backward compatibility."""

    objective: ObjectiveOut | None
    objectives: list[ObjectiveOut] = []
    constraints: list[ConstraintOut]
    active_program: ProgramStrategy | None = None
