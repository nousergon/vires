"""Deterministic post-workout autoregulation — the *micro* adaptation loop.

After a session that fulfilled a coach-planned workout is finished, compare what
the athlete actually did against the prescription and nudge the load of the next
few planned occurrences of each exercise. No LLM: this is the same double-
progression arithmetic the materializer already trusts, so it is reproducible
and unit-testable. The *macro* loop (event-triggered LLM re-plan, propose-and-
confirm) is separate — see vires-ops#9.

Rule (per exercise, double progression):
- **progress** (+1 plate step): completed every prescribed set at or above the
  target weight AND hit the target reps on all of them.
- **back_off** (-1 plate step): failed to complete the prescribed sets, or fell
  two or more reps short while at/above the target weight.
- **hold** (no change): anything in between (e.g. scaled the weight down, or
  just missed reps) — don't yo-yo the plan.

The verdict's load delta is applied to the **next N** future planned
occurrences of that exercise in the same program (``AUTOREG_LOOKAHEAD``), so the
adjustment is bounded and reversible and never disturbs the far-future peak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, get_or_create_settings
from api.db.models import PlannedExercise, PlannedWorkout, WorkoutSession
from api.services.coach.audit import record_plan_change
from api.services.coach.materialize import PLATE_INCREMENT, _round_to_plate

# How many future occurrences of an exercise a single session may adjust.
AUTOREG_LOOKAHEAD = 3
# Load/hold step for timed (duration) exercises.
DURATION_STEP_SECONDS = 5
_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Pure assessment (no DB) — what should happen to this exercise's load?
# --------------------------------------------------------------------------- #
@dataclass
class SetResult:
    reps: int | None
    weight: float | None
    duration_seconds: int | None
    completed: bool


@dataclass
class ExercisePerformance:
    exercise_id: int
    is_timed: bool
    target_sets: int | None
    target_reps: int | None
    target_weight: float | None
    target_duration_seconds: int | None
    sets: list[SetResult] = field(default_factory=list)


@dataclass
class Adjustment:
    exercise_id: int
    verdict: str  # 'progress' | 'hold' | 'back_off'
    weight_delta: float = 0.0
    duration_delta_seconds: int = 0

    @property
    def is_change(self) -> bool:
        return self.weight_delta != 0.0 or self.duration_delta_seconds != 0


def _hold(exercise_id: int) -> Adjustment:
    return Adjustment(exercise_id, "hold")


def assess_exercise(perf: ExercisePerformance, weight_unit: str) -> Adjustment:
    """Decide progress / hold / back_off for one exercise from its logged sets."""
    completed = [s for s in perf.sets if s.completed]
    if not completed:
        return _hold(perf.exercise_id)
    target_sets = perf.target_sets or len(completed)
    all_sets_done = len(completed) >= target_sets

    if perf.is_timed:
        tgt = perf.target_duration_seconds
        durations = [s.duration_seconds for s in completed if s.duration_seconds is not None]
        if tgt is None or not durations:
            return _hold(perf.exercise_id)
        if all_sets_done and min(durations) >= tgt:
            return Adjustment(
                perf.exercise_id, "progress", duration_delta_seconds=DURATION_STEP_SECONDS
            )
        if not all_sets_done:
            return Adjustment(
                perf.exercise_id, "back_off", duration_delta_seconds=-DURATION_STEP_SECONDS
            )
        return _hold(perf.exercise_id)

    # Weighted (double progression).
    tgt_reps, tgt_weight = perf.target_reps, perf.target_weight
    if tgt_reps is None or tgt_weight is None:
        return _hold(perf.exercise_id)
    reps = [s.reps for s in completed if s.reps is not None]
    weights = [s.weight for s in completed if s.weight is not None]
    if not reps or not weights:
        return _hold(perf.exercise_id)
    step = PLATE_INCREMENT.get(weight_unit, PLATE_INCREMENT["lb"])
    hit_weight = min(weights) >= tgt_weight - _EPS

    if all_sets_done and hit_weight and min(reps) >= tgt_reps:
        return Adjustment(perf.exercise_id, "progress", weight_delta=step)
    missed_sets = len(completed) < target_sets
    reps_short_at_weight = hit_weight and min(reps) <= tgt_reps - 2
    if missed_sets or reps_short_at_weight:
        return Adjustment(perf.exercise_id, "back_off", weight_delta=-step)
    return _hold(perf.exercise_id)


# --------------------------------------------------------------------------- #
# Applied result (returned for logging / the future audit log — vires-ops#18)
# --------------------------------------------------------------------------- #
@dataclass
class AppliedAdjustment:
    exercise_id: int
    verdict: str
    weight_delta: float
    duration_delta_seconds: int
    occurrences_adjusted: int


# --------------------------------------------------------------------------- #
# DB-backed orchestrator
# --------------------------------------------------------------------------- #
def _performance_from_session(session: WorkoutSession) -> list[ExercisePerformance]:
    perfs: list[ExercisePerformance] = []
    for se in session.exercises:
        perfs.append(
            ExercisePerformance(
                exercise_id=se.exercise_id,
                is_timed=se.exercise.is_timed,
                target_sets=se.target_sets,
                target_reps=se.target_reps,
                target_weight=se.target_weight,
                target_duration_seconds=se.target_duration_seconds,
                sets=[
                    SetResult(
                        reps=s.reps,
                        weight=s.weight,
                        duration_seconds=s.duration_seconds,
                        completed=s.completed_at is not None and not s.is_warmup,
                    )
                    for s in se.sets
                ],
            )
        )
    return perfs


def _next_planned_exercises(
    db: Session,
    ident: Identity,
    program_id: int,
    exercise_id: int,
    today: date,
    limit: int,
) -> list[PlannedExercise]:
    """The next ``limit`` still-planned future occurrences of an exercise in a
    program, chronological."""
    return list(
        db.scalars(
            select(PlannedExercise)
            .join(PlannedWorkout, PlannedExercise.planned_workout_id == PlannedWorkout.id)
            .where(
                PlannedWorkout.tenant_id == ident.tenant_id,
                PlannedWorkout.user_id == ident.user_id,
                PlannedWorkout.program_id == program_id,
                PlannedWorkout.status == "planned",
                PlannedWorkout.scheduled_date >= today,
                PlannedExercise.exercise_id == exercise_id,
            )
            .order_by(PlannedWorkout.scheduled_date)
            .limit(limit)
        ).all()
    )


def _apply(pe: PlannedExercise, adj: Adjustment, weight_unit: str) -> bool:
    """Mutate one planned exercise by the adjustment; True if anything changed."""
    step = PLATE_INCREMENT.get(weight_unit, PLATE_INCREMENT["lb"])
    changed = False
    if adj.weight_delta and pe.target_weight is not None:
        # Never drop below a single plate; snap to the plate grid.
        pe.target_weight = _round_to_plate(
            max(step, pe.target_weight + adj.weight_delta), step
        )
        changed = True
    if adj.duration_delta_seconds and pe.target_duration_seconds is not None:
        pe.target_duration_seconds = max(
            DURATION_STEP_SECONDS, pe.target_duration_seconds + adj.duration_delta_seconds
        )
        changed = True
    return changed


def autoregulate_after_session(
    db: Session, ident: Identity, session: WorkoutSession, today: date | None = None
) -> list[AppliedAdjustment]:
    """Adjust upcoming planned loads from a just-finished session's performance.

    No-op (returns ``[]``) unless the session fulfilled a planned workout that
    belongs to a coach program. Does NOT commit — the caller owns the transaction
    so the adjustment lands atomically with the finish."""
    if today is None:
        today = date.today()
    planned_id = session.planned_workout_id
    if planned_id is None:
        return []
    pw = db.get(PlannedWorkout, planned_id)
    if pw is None or pw.program_id is None:
        return []

    weight_unit = get_or_create_settings(db, ident).weight_unit
    applied: list[AppliedAdjustment] = []
    for perf in _performance_from_session(session):
        adj = assess_exercise(perf, weight_unit)
        if not adj.is_change:
            continue
        upcoming = _next_planned_exercises(
            db, ident, pw.program_id, perf.exercise_id, today, AUTOREG_LOOKAHEAD
        )
        n = sum(1 for pe in upcoming if _apply(pe, adj, weight_unit))
        if n:
            applied.append(
                AppliedAdjustment(
                    exercise_id=perf.exercise_id,
                    verdict=adj.verdict,
                    weight_delta=adj.weight_delta,
                    duration_delta_seconds=adj.duration_delta_seconds,
                    occurrences_adjusted=n,
                )
            )

    if applied:
        progressed = sum(1 for a in applied if a.verdict == "progress")
        backed_off = sum(1 for a in applied if a.verdict == "back_off")
        record_plan_change(
            db,
            ident,
            source="autoregulation",
            program_id=pw.program_id,
            session_id=session.id,
            trigger="performance",
            summary=(
                f"Autoregulated {len(applied)} exercise(s) from your last session "
                f"({progressed} up, {backed_off} down)."
            ),
            detail={
                "adjustments": [
                    {
                        "exercise_id": a.exercise_id,
                        "verdict": a.verdict,
                        "weight_delta": a.weight_delta,
                        "duration_delta_seconds": a.duration_delta_seconds,
                        "occurrences_adjusted": a.occurrences_adjusted,
                    }
                    for a in applied
                ]
            },
        )
    return applied
