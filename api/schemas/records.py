"""Personal-record schemas.

Records are DERIVED from performed (completed, non-warmup) sets — there's no PR
table; they're computed on read so they always reflect current history and can be
sliced by time window (all-time / last year / quarter / month).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from api.schemas.exercise import ExerciseBrief


class RecordMetric(BaseModel):
    """A single best, with the set that achieved it."""

    value: float  # the metric (e1RM, weight, volume, reps, or hold-seconds)
    weight: float | None = None
    reps: int | None = None
    date: date  # session date it was hit


class ExerciseRecords(BaseModel):
    exercise: ExerciseBrief
    is_timed: bool
    # Weight-based bests (None for timed/bodyweight where inapplicable):
    est_1rm: RecordMetric | None = None  # Epley, from sets of 1-12 reps
    heaviest: RecordMetric | None = None
    best_set_volume: RecordMetric | None = None  # max weight*reps in one set
    most_reps: RecordMetric | None = None  # max reps in one set (non-timed)
    longest_hold: RecordMetric | None = None  # max duration, seconds (timed only)
