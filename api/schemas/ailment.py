"""Ailment episode + check-in schemas (date-anchored injury tracking)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AilmentStatus = Literal["active", "improving", "resolved"]


class AilmentCheckInOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ailment_id: int
    check_in_date: date
    severity: int
    note: str | None
    created_at: datetime


class AilmentEpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    onset_date: date
    notes: str | None
    status: str
    resolved_at: date | None
    created_at: datetime
    updated_at: datetime
    latest_severity: int | None = None
    latest_check_in_date: date | None = None
    check_ins: list[AilmentCheckInOut] = Field(default_factory=list)


class AilmentEpisodeCreate(BaseModel):
    label: str = Field(min_length=1)
    onset_date: date | None = None
    notes: str | None = None
    # Optional same-day severity when registering the episode.
    initial_severity: int | None = Field(default=None, ge=0, le=10)


class AilmentEpisodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1)
    notes: str | None = None
    status: AilmentStatus | None = None


class AilmentCheckInCreate(BaseModel):
    check_in_date: date | None = None
    severity: int = Field(ge=0, le=10)
    note: str | None = None

    @field_validator("severity")
    @classmethod
    def _whole_severity(cls, v: int) -> int:
        return int(v)


class PendingAilmentCheckIn(BaseModel):
    """An active/improving episode with no check-in on the requested day."""

    ailment: AilmentEpisodeOut
    last_severity: int | None = None
    last_check_in_date: date | None = None
