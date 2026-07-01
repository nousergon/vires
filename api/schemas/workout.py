"""Workout session / logging schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.exercise import ExerciseBrief, ExercisePerformance

# Coarse terrain classes accepted for a ruck (→ Pandolf terrain factor server-side).
Terrain = Literal["treadmill", "road", "trail", "offtrail", "snow"]


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


# --------------------------------------------------------------------------- #
# Ruck (loaded-cardio) — Tier 0 quick-log
# --------------------------------------------------------------------------- #
class RuckLogIn(BaseModel):
    """Quick-log a completed ruck. Numbers arrive in the USER'S display units
    (weights in the account's ``weight_unit``; distance/elevation in mi/ft when
    that unit is ``lb``, km/m when ``kg``). The router converts to canonical SI
    once, at the boundary."""

    pack_weight: float = Field(gt=0, description="Carried load, in the user's weight unit")
    bodyweight: float = Field(gt=0, description="Body mass, in the user's weight unit")
    distance: float | None = Field(default=None, ge=0)
    elevation_gain: float | None = Field(default=None, ge=0)
    duration_s: int | None = Field(default=None, ge=0)
    terrain: Terrain = "trail"
    name: str | None = None
    # Optional backdate (e.g. logging yesterday's ruck). Defaults to now server-side.
    started_at: datetime | None = None


class RuckDetailOut(BaseModel):
    """Canonical SI ruck detail + the derived metabolic cost. The frontend converts
    back to the user's display units for rendering."""

    pack_weight_kg: float
    bodyweight_kg: float
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    duration_s: int | None = None
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
    # Present only for session_type == 'ruck'.
    ruck: RuckDetailOut | None = None


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
    # Compact ruck facts for the history row (None for strength sessions).
    ruck: RuckDetailOut | None = None
