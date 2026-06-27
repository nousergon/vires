"""User settings schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WeightUnit = Literal["lb", "kg"]


class SettingsOut(BaseModel):
    weight_unit: WeightUnit
    default_rest_seconds: int
    default_sets: int
    default_reps: int


class SettingsUpdate(BaseModel):
    weight_unit: WeightUnit | None = None
    default_rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    default_sets: int | None = Field(default=None, ge=1, le=100)
    default_reps: int | None = Field(default=None, ge=1, le=100)
