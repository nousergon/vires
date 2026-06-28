"""Deterministic materialization of a ``ProgramSpec`` into dated workouts.

Pure functions only — **no LLM, no DB**. The router builds a ``MaterializeContext``
from the database and hands it here; keeping this layer side-effect-free is what
makes the coach's output reproducible and unit-testable (the LLM proposes a
declarative spec; the arithmetic lives here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from api.schemas.coach import ExerciseProgression, ProgramSpec

# Smallest weight change we'll prescribe, by unit (a standard plate pair step).
PLATE_INCREMENT = {"lb": 2.5, "kg": 1.25}
DELOAD_LOAD_FACTOR = 0.9  # deload weeks prescribe ~10% lighter

# Canonical day name -> Python weekday index (Monday=0 … Sunday=6).
_WEEKDAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _weekday_index(weekday: str) -> int:
    return _WEEKDAY_INDEX.get(str(weekday).strip().lower(), 0)


# --------------------------------------------------------------------------- #
# Context the router assembles from the DB (kept DB-free here for testability)
# --------------------------------------------------------------------------- #
@dataclass
class TemplateExerciseCtx:
    exercise_id: int
    name: str
    is_timed: bool
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    last_weight: float | None = None  # most recent logged weight for this exercise


@dataclass
class TemplateCtx:
    template_id: int
    name: str
    exercises: list[TemplateExerciseCtx] = field(default_factory=list)


@dataclass
class MaterializeContext:
    templates: dict[int, TemplateCtx]
    weight_unit: str = "lb"


# --------------------------------------------------------------------------- #
# Output (plain data; the router turns this into ORM rows or a preview)
# --------------------------------------------------------------------------- #
@dataclass
class PlannedExerciseData:
    exercise_id: int
    exercise_name: str
    order_index: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


@dataclass
class PlannedWorkoutData:
    template_id: int | None
    scheduled_date: date
    name: str
    week_index: int
    exercises: list[PlannedExerciseData] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# math helpers
# --------------------------------------------------------------------------- #
def _first_on_or_after(start: date, weekday: int) -> date:
    """First date >= ``start`` whose weekday (0=Mon) equals ``weekday``."""
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def _interp(start: float, end: float, f: float, mode: str, steps: int | None) -> float:
    """Value at fraction ``f`` in [0,1] from ``start`` to ``end`` for the given mode."""
    if mode == "constant":
        return start
    if mode == "step":
        n = steps if steps and steps > 1 else 2
        # Snap f to one of n discrete levels, then interpolate at that level.
        level = round(f * (n - 1))
        f = level / (n - 1)
    # linear / percent_of_start / fallback all interpolate linearly in f
    return start + (end - start) * f


def _round_to_plate(value: float | None, plate: float) -> float | None:
    if value is None:
        return None
    snapped = round(value / plate) * plate
    return round(snapped, 2)  # kill float noise (e.g. 2.4999999)


def _round_reps(value: float | None) -> int | None:
    if value is None:
        return None
    return max(1, round(value))


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #
def _find_progression(
    spec: ProgramSpec, template_id: int, exercise_id: int
) -> ExerciseProgression | None:
    """Most specific matching progression: exercise-specific beats template-wide."""
    specific = None
    template_wide = None
    for p in spec.progressions:
        if p.template_id != template_id:
            continue
        if p.exercise_id == exercise_id:
            specific = p
        elif p.exercise_id is None:
            template_wide = p
    return specific or template_wide


def _seed_weight(prog: ExerciseProgression | None, te: TemplateExerciseCtx) -> float | None:
    """Starting weight: explicit spec seed -> template target -> last logged -> None."""
    if prog is not None and prog.seed_weight is not None:
        return prog.seed_weight
    if te.target_weight is not None:
        return te.target_weight
    return te.last_weight


def materialize(spec: ProgramSpec, ctx: MaterializeContext) -> list[PlannedWorkoutData]:
    """Expand a spec into one ``PlannedWorkoutData`` per (week, schedule entry)."""
    plate = PLATE_INCREMENT.get(ctx.weight_unit, PLATE_INCREMENT["lb"])
    out: list[PlannedWorkoutData] = []
    dw = spec.duration_weeks

    for entry in spec.schedule:
        tpl = ctx.templates.get(entry.template_id)
        if tpl is None:
            continue  # unknown template (grounding should prevent this) — skip, don't guess
        first_date = _first_on_or_after(spec.start_date, _weekday_index(entry.weekday))

        for w in range(1, dw + 1):
            f = 0.0 if dw == 1 else (w - 1) / (dw - 1)
            deload = w in spec.deload_weeks
            scheduled = first_date + timedelta(days=(w - 1) * 7)
            exercises: list[PlannedExerciseData] = []

            for i, te in enumerate(tpl.exercises):
                prog = _find_progression(spec, entry.template_id, te.exercise_id)
                sets = prog.sets if (prog and prog.sets) else te.target_sets

                if te.is_timed:
                    exercises.append(
                        PlannedExerciseData(
                            exercise_id=te.exercise_id,
                            exercise_name=te.name,
                            order_index=i,
                            target_sets=sets,
                            target_duration_seconds=te.target_duration_seconds,
                            rest_seconds=te.rest_seconds,
                            notes="Deload" if deload else None,
                        )
                    )
                    continue

                # reps
                if prog and prog.reps:
                    reps = _round_reps(
                        _interp(prog.reps.start, prog.reps.end, f, prog.reps.mode, prog.reps.steps)
                    )
                else:
                    reps = te.target_reps

                # weight
                weight = _compute_weight(prog, te, f, plate)
                note = None
                if deload:
                    if weight is not None:
                        weight = _round_to_plate(weight * DELOAD_LOAD_FACTOR, plate)
                    note = "Deload"

                exercises.append(
                    PlannedExerciseData(
                        exercise_id=te.exercise_id,
                        exercise_name=te.name,
                        order_index=i,
                        target_sets=sets,
                        target_reps=reps,
                        target_weight=weight,
                        rest_seconds=te.rest_seconds,
                        notes=note,
                    )
                )

            out.append(
                PlannedWorkoutData(
                    template_id=entry.template_id,
                    scheduled_date=scheduled,
                    name=f"{tpl.name} — Week {w}",
                    week_index=w,
                    exercises=exercises,
                )
            )

    out.sort(key=lambda p: (p.scheduled_date, p.template_id or 0))
    return out


def _compute_weight(
    prog: ExerciseProgression | None, te: TemplateExerciseCtx, f: float, plate: float
) -> float | None:
    seed = _seed_weight(prog, te)
    if prog is None or prog.weight is None:
        # no weight progression -> hold the seed weight flat (rounded), if known
        return _round_to_plate(seed, plate)
    wc = prog.weight
    if wc.mode == "percent_of_start":
        if seed is None:
            return None  # can't take a percentage of an unknown starting weight
        return _round_to_plate(seed * _interp(wc.start, wc.end, f, "linear", None), plate)
    # absolute weight curve (linear / step / constant)
    return _round_to_plate(_interp(wc.start, wc.end, f, wc.mode, wc.steps), plate)


def end_date(spec: ProgramSpec) -> date:
    """Last scheduled date across all schedule entries (for Program.end_date)."""
    last = spec.start_date
    for entry in spec.schedule:
        first = _first_on_or_after(spec.start_date, _weekday_index(entry.weekday))
        d = first + timedelta(days=(spec.duration_weeks - 1) * 7)
        last = max(last, d)
    return last
