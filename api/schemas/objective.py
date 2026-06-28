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
    sport: str | None = None
    # Omit to auto-fill from the authored profile for ``sport`` (if one exists).
    demands_profile: dict[str, Any] | None = None
    is_primary: bool = False

    @model_validator(mode="after")
    def _dated_needs_target(self) -> ObjectiveCreate:
        if self.kind == "dated" and self.target_date is None:
            raise ValueError("target_date is required when kind='dated'")
        return self


class ObjectiveUpdate(BaseModel):
    """Partial update. Cross-field (dated ⇒ target_date) is validated in the
    router against the merged row, since any field may be absent here."""

    name: str | None = Field(default=None, min_length=1)
    kind: ObjectiveKind | None = None
    target_date: date | None = None
    sport: str | None = None
    demands_profile: dict[str, Any] | None = None
    is_primary: bool | None = None


class ObjectiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    target_date: date | None
    sport: str | None
    demands_profile: dict[str, Any] | None
    is_primary: bool
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
class ActiveObjectiveOut(BaseModel):
    """The active primary objective (if any) + the active constraints — the
    context objective-driven generation runs against."""

    objective: ObjectiveOut | None
    constraints: list[ConstraintOut]
