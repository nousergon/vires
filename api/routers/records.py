"""Personal records — per-exercise bests, all-time or within a time window.

Derived on read from performed sets (``completed_at`` set, non-warmup): a record
must be an actually-trained set, never a seeded/planned target. Single-user MVP →
computing in Python over the user's set history is plenty fast.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import Exercise, SessionExercise, SetEntry, WorkoutSession
from api.db.session import get_db
from api.schemas.records import ExerciseRecords, RecordMetric
from api.serializers import to_exercise_brief

router = APIRouter(prefix="/records", tags=["records"])

# Days of history per window; "all" => no lower bound.
_WINDOW_DAYS = {"all": None, "year": 365, "quarter": 90, "month": 30}
# Epley is only meaningful in the strength rep range; ignore very high-rep sets.
_E1RM_MAX_REPS = 12


def _now() -> datetime:
    return datetime.now(UTC)


def _epley(weight: float, reps: int) -> float:
    return weight * (1 + reps / 30)


@dataclass
class _PerformedSet:
    weight: float | None
    reps: int | None
    duration: int | None
    on: date


@router.get("", response_model=list[ExerciseRecords])
def list_records(
    window: str = Query("all", pattern="^(all|year|quarter|month)$"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[ExerciseRecords]:
    days = _WINDOW_DAYS[window]
    cutoff = _now() - timedelta(days=days) if days is not None else None

    q = (
        select(
            SessionExercise.exercise_id,
            SetEntry.weight,
            SetEntry.reps,
            SetEntry.duration_seconds,
            WorkoutSession.started_at,
        )
        .join(SetEntry, SetEntry.session_exercise_id == SessionExercise.id)
        .join(WorkoutSession, WorkoutSession.id == SessionExercise.session_id)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
            SetEntry.completed_at.is_not(None),  # performed, not a planned/seeded set
            SetEntry.is_warmup.is_(False),
        )
    )
    if cutoff is not None:
        q = q.where(WorkoutSession.started_at >= cutoff)

    by_exercise: dict[int, list[_PerformedSet]] = defaultdict(list)
    for exercise_id, weight, reps, duration, started_at in db.execute(q).all():
        by_exercise[exercise_id].append(
            _PerformedSet(weight=weight, reps=reps, duration=duration, on=started_at.date())
        )

    out: list[ExerciseRecords] = []
    for exercise_id, sets in by_exercise.items():
        ex = db.get(Exercise, exercise_id)
        if ex is None:
            continue
        out.append(_records_for(ex, sets))

    # Headline-first: strongest e1RM, then longest hold, then name.
    out.sort(
        key=lambda r: (
            -(r.est_1rm.value if r.est_1rm else 0),
            -(r.longest_hold.value if r.longest_hold else 0),
            r.exercise.name.lower(),
        )
    )
    return out


def _records_for(ex: Exercise, sets: list[_PerformedSet]) -> ExerciseRecords:
    rec = ExerciseRecords(exercise=to_exercise_brief(ex), is_timed=ex.is_timed)

    if ex.is_timed:
        holds = [s for s in sets if s.duration]
        if holds:
            best = max(holds, key=lambda s: s.duration)
            rec.longest_hold = RecordMetric(value=float(best.duration), date=best.on)
        return rec

    weighted = [s for s in sets if s.weight and s.weight > 0]
    repped = [s for s in sets if s.reps and s.reps > 0]

    if weighted:
        h = max(weighted, key=lambda s: s.weight)
        rec.heaviest = RecordMetric(value=h.weight, weight=h.weight, reps=h.reps, date=h.on)

        vol = max(weighted, key=lambda s: s.weight * (s.reps or 1))
        rec.best_set_volume = RecordMetric(
            value=round(vol.weight * (vol.reps or 1), 2),
            weight=vol.weight,
            reps=vol.reps,
            date=vol.on,
        )

        e1rm = [s for s in weighted if s.reps and 1 <= s.reps <= _E1RM_MAX_REPS]
        if e1rm:
            best = max(e1rm, key=lambda s: _epley(s.weight, s.reps))
            rec.est_1rm = RecordMetric(
                value=round(_epley(best.weight, best.reps), 1),
                weight=best.weight,
                reps=best.reps,
                date=best.on,
            )

    if repped:
        r = max(repped, key=lambda s: s.reps)
        rec.most_reps = RecordMetric(value=float(r.reps), weight=r.weight, reps=r.reps, date=r.on)

    return rec
