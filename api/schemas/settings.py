"""User settings schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.coach import Weekday

WeightUnit = Literal["lb", "kg"]


class SettingsOut(BaseModel):
    weight_unit: WeightUnit
    default_rest_seconds: int
    default_sets: int
    default_reps: int
    timer_sound: bool
    timer_vibration: bool
    timer_notification: bool
    timer_keep_awake: bool
    # Durable weekly-lifting day preference the coach honors on every
    # generation (e.g. ["monday", "thursday"]) — empty = no standing
    # preference, unchanged behavior.
    preferred_weekdays: list[Weekday]


class SettingsUpdate(BaseModel):
    weight_unit: WeightUnit | None = None
    default_rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    default_sets: int | None = Field(default=None, ge=1, le=100)
    default_reps: int | None = Field(default=None, ge=1, le=100)
    timer_sound: bool | None = None
    timer_vibration: bool | None = None
    timer_notification: bool | None = None
    timer_keep_awake: bool | None = None
    preferred_weekdays: list[Weekday] | None = None
