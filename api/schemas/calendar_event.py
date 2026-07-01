"""CalendarEvent schemas (athletic calendar — vires-ops#30/#31).

A ``CalendarEvent`` is a training-load CONSTRAINT the coach trains *around*
(a race, a weekly league game, a ski trip, a rehab window) — distinct from
``Objective``, which is a goal the coach peaks *toward*. ``load`` is a small
structured sub-object (regions/intensity/duration) rather than free-form JSON
like ``Objective.demands_profile``, since the coach's load-accounting needs a
fixed, typed shape to reason over.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventType = Literal["competition", "league", "recreation", "travel", "rehab"]
Recurrence = Literal["none", "weekly"]
LoadRegions = Literal["legs", "upper", "full", "core", "none"]
LoadIntensity = Literal["light", "moderate", "hard"]


class EventLoad(BaseModel):
    """Coarse, structured estimate of the training load an event represents —
    the axis that makes events useful to the coach (load-accounting, #33)."""

    regions: LoadRegions
    intensity: LoadIntensity
    duration_min: int | None = Field(default=None, gt=0)


class CalendarEventCreate(BaseModel):
    name: str = Field(min_length=1)
    sport: str | None = None
    type: EventType
    event_date: date
    # Last day of a multi-day event (>= event_date); omit for a single-day event.
    event_end_date: date | None = None
    recurrence: Recurrence = "none"
    load: EventLoad | None = None
    notes: str | None = None
    # Set only when this event IS itself a peak target the objective anchors to.
    objective_id: int | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> CalendarEventCreate:
        if self.event_end_date is not None and self.event_end_date < self.event_date:
            raise ValueError("event_end_date must be on or after event_date")
        return self


class CalendarEventUpdate(BaseModel):
    """Partial update. Cross-field (event_end_date >= event_date) is validated
    in the router against the merged row, since any field may be absent here."""

    name: str | None = Field(default=None, min_length=1)
    sport: str | None = None
    type: EventType | None = None
    event_date: date | None = None
    event_end_date: date | None = None
    recurrence: Recurrence | None = None
    load: EventLoad | None = None
    notes: str | None = None
    objective_id: int | None = None


class CalendarEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sport: str | None
    type: str
    event_date: date
    event_end_date: date | None
    recurrence: str
    load: EventLoad | None
    notes: str | None
    objective_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CalendarEventOccurrence(BaseModel):
    """One concrete occurrence of a (possibly recurring) event within a queried
    date window — the server-side expansion of ``recurrence='weekly'`` events.
    Never persisted; computed on read (see
    ``api.services.calendar_events.expand_occurrences``)."""

    event: CalendarEventOut
    # The concrete date this occurrence falls on within the window (for a
    # 'none' recurrence event this is always ``event.event_date``).
    occurrence_date: date
    # Last day of this occurrence (mirrors event_end_date for a single
    # occurrence; recurring events don't span multiple days).
    occurrence_end_date: date | None = None
