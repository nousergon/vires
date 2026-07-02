"""Workout session / logging schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from api.schemas.calendar_event import LoadIntensity, LoadRegions
from api.schemas.exercise import ExerciseBrief, ExercisePerformance

# Coarse terrain classes accepted for a route-capable activity (→ Pandolf
# terrain factor server-side).
Terrain = Literal["treadmill", "road", "trail", "offtrail", "snow"]

# How the route stats were entered — the flexible-input modes all land here.
RouteSource = Literal["manual", "route_search", "route_draw", "gpx"]


class WorkoutStart(BaseModel):
    template_id: int | None = None  # None => empty/ad-hoc workout
    name: str | None = None


class SetIn(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    set_number: int | None = None  # auto-assigned (next) when omitted
    # Whether the new set is already performed. Defaults True (a directly-logged
    # set). The app passes False from "+ Add set" so an empty row appears unchecked
    # for the user to fill in and tick off themselves.
    done: bool = True


class SetUpdate(BaseModel):
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool | None = None
    # Mark the set done/undone — stamps (or clears) completed_at server-side.
    done: bool | None = None


class SetOut(BaseModel):
    id: int
    set_number: int
    reps: int | None = None
    weight: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    is_warmup: bool = False
    completed_at: datetime | None = None


class SessionExerciseIn(BaseModel):
    exercise_id: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class SessionExerciseUpdate(BaseModel):
    """Patch a session exercise in place: tweak its rest/targets or reorder it.

    All fields optional; only those present (``exclude_unset``) are applied.
    ``order_index`` drives drag-free reordering (the app swaps adjacent rows).
    """

    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    order_index: int | None = None


class SessionExerciseOut(BaseModel):
    id: int
    order_index: int
    exercise: ExerciseBrief
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[SetOut]
    # Most recent prior performance of this exercise (the "last time" hint).
    previous_performance: ExercisePerformance | None = None


class ActivityTemplateOut(BaseModel):
    """One entry in the fixed activity-template catalog (``GET
    /workouts/activity-templates``) — a starting point the quick-log form
    prefills and the user can freely edit. ``route_capable`` templates
    (walk/run/hike) additionally get the route-capture UI + optional
    pack-weight section on the frontend."""

    key: str
    label: str
    regions: LoadRegions
    intensity: LoadIntensity
    route_capable: bool = False


# --------------------------------------------------------------------------- #
# Activity (cross-training + locomotion) — Tier 0 quick-log
# --------------------------------------------------------------------------- #
class ActivityLogIn(BaseModel):
    """Quick-log a completed activity — cross-training (climbing, swimming,
    yoga, ...) or locomotion (walk/run/hike). Route + load-carriage fields
    are optional on every template: only walk/run/hike surface their picker
    in the UI, but the backend doesn't gate on ``template_key`` (a custom
    entry could plausibly carry a route too).

    ``regions``/``intensity`` are always present — a template prefills them,
    but 'custom' (freeform, no template) still requires the user to pick a
    coarse estimate rather than leaving it unset, since that's the whole
    point of logging this: giving the coach something to reason about.

    Numbers arrive in the USER'S display units (weights in the account's
    ``weight_unit``; distance/elevation in mi/ft when that unit is ``lb``,
    km/m when ``kg``). The router converts to canonical SI once, at the
    boundary.
    """

    name: str = Field(min_length=1, description="Display name, e.g. 'Indoor top-rope'")
    template_key: str = "custom"
    duration_s: int | None = Field(default=None, ge=0)
    regions: LoadRegions = "full"
    intensity: LoadIntensity = "moderate"
    # Optional backdate (e.g. logging yesterday's session). Defaults to now server-side.
    started_at: datetime | None = None

    # Route capture — optional for every template.
    distance: float | None = Field(default=None, ge=0)
    elevation_gain: float | None = Field(default=None, ge=0)
    terrain: Terrain = "trail"
    # Which input mode produced the route stats (manual entry, trail search,
    # drawn route, or GPX import). Distance/elevation are always user-editable
    # regardless of source.
    source: RouteSource = "manual"

    # Optional load-carriage. Never required to submit — "i don't expect
    # people with light packs to bother weighing their pack" is the product
    # call here. bodyweight is required IFF pack_weight is given: Pandolf's
    # load ratio (L/W) is undefined without body mass, but bodyweight alone
    # with no pack is meaningless and simply ignored.
    pack_weight: float | None = Field(
        default=None, gt=0, description="Carried load, in the user's weight unit"
    )
    bodyweight: float | None = Field(
        default=None, gt=0, description="Body mass, in the user's weight unit"
    )

    @model_validator(mode="after")
    def _bodyweight_required_with_pack(self) -> ActivityLogIn:
        if self.pack_weight is not None and self.bodyweight is None:
            raise ValueError("bodyweight is required when pack_weight is given")
        return self


class ActivityDetailOut(BaseModel):
    template_key: str = "custom"
    duration_s: int | None = None
    regions: LoadRegions
    intensity: LoadIntensity
    pack_weight_kg: float | None = None
    bodyweight_kg: float | None = None
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    terrain: str = "trail"
    metabolic_cost_kj: float | None = None
    source: str = "manual"


class WorkoutSessionOut(BaseModel):
    id: int
    session_type: str = "strength"
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    notes: str | None = None
    template_id: int | None = None
    exercises: list[SessionExerciseOut]
    # Present only for session_type == 'activity'.
    activity: ActivityDetailOut | None = None


class WorkoutSummary(BaseModel):
    id: int
    session_type: str = "strength"
    name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    exercise_count: int
    set_count: int
    total_volume: float = Field(
        default=0.0, description="Sum of reps*weight over completed working sets"
    )
    # Compact activity facts for the history row (None otherwise).
    activity: ActivityDetailOut | None = None
