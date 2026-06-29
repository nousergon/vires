"""Deterministic materialization of a ``ProgramSpec`` into dated workouts.

Pure functions only — **no LLM, no DB**. The router builds a ``MaterializeContext``
from the database and hands it here; keeping this layer side-effect-free is what
makes the coach's output reproducible and unit-testable (the LLM proposes a
declarative spec; the arithmetic lives here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from api.schemas.coach import ExerciseProgression, ProgramSpec, ScheduleEntry

# Smallest weight change we'll prescribe, by unit (a standard plate pair step).
PLATE_INCREMENT = {"lb": 2.5, "kg": 1.25}
DELOAD_LOAD_FACTOR = 0.9  # deload weeks prescribe ~10% lighter


# --------------------------------------------------------------------------- #
# Season blocks — a spec is either flat (one block) or phased (a block per
# objective). Normalizing both into a list of blocks lets every consumer
# (materialize, end_date, grounding) share one code path.
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    objective_id: int | None
    start_date: date
    duration_weeks: int
    schedule: list[ScheduleEntry]
    progressions: list[ExerciseProgression]
    deload_weeks: list[int]


def program_blocks(spec: ProgramSpec) -> list[Block]:
    """The spec's training blocks: its phases, or a single block from the flat
    fields when not phased."""
    if spec.phases:
        return [
            Block(
                objective_id=p.objective_id,
                start_date=p.start_date,
                duration_weeks=p.duration_weeks,
                schedule=p.schedule,
                progressions=p.progressions,
                deload_weeks=p.deload_weeks,
            )
            for p in spec.phases
        ]
    return [
        Block(
            objective_id=None,
            start_date=spec.start_date,
            duration_weeks=spec.duration_weeks,
            schedule=spec.schedule,
            progressions=spec.progressions,
            deload_weeks=spec.deload_weeks,
        )
    ]


def all_schedule(spec: ProgramSpec) -> list[ScheduleEntry]:
    """Every schedule entry across all blocks (for grounding/validation)."""
    return [e for b in program_blocks(spec) for e in b.schedule]


def all_progressions(spec: ProgramSpec) -> list[ExerciseProgression]:
    """Every progression across all blocks (for grounding/validation)."""
    return [p for b in program_blocks(spec) for p in b.progressions]


def start_date_of(spec: ProgramSpec) -> date:
    """The program's overall start — the earliest block start."""
    return min(b.start_date for b in program_blocks(spec))

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
# New-routine resolution
#
# The coach may AUTHOR routines (``spec.new_routines``) so a plan can train an
# objective the user has no existing routine for. Schedule/progression entries
# reference these by ``routine_key``. Two resolution paths share one rewrite:
#  * PREVIEW (pure, here): synthesize each new routine as a negative-id template,
#    rewrite routine_key -> that id, so the existing materializer expands it with
#    no DB write.
#  * SAVE (router, with DB): persist each new routine as a real WorkoutTemplate,
#    then ``rewrite_routine_refs`` with the real ids.
# --------------------------------------------------------------------------- #
ExerciseMeta = dict[int, tuple[str, bool]]  # exercise_id -> (name, is_timed)


def rewrite_routine_refs(spec: ProgramSpec, key_to_id: dict[str, int]) -> ProgramSpec:
    """Return a spec with every ``routine_key`` reference rewritten to a concrete
    ``template_id`` and ``new_routines`` cleared (the routines now exist)."""

    def _entry(e: ScheduleEntry) -> ScheduleEntry:
        if e.routine_key is None:
            return e
        return e.model_copy(
            update={"template_id": key_to_id[e.routine_key], "routine_key": None}
        )

    def _prog(p: ExerciseProgression) -> ExerciseProgression:
        if p.routine_key is None:
            return p
        return p.model_copy(
            update={"template_id": key_to_id[p.routine_key], "routine_key": None}
        )

    phases = [
        ph.model_copy(
            update={
                "schedule": [_entry(e) for e in ph.schedule],
                "progressions": [_prog(p) for p in ph.progressions],
            }
        )
        for ph in spec.phases
    ]
    return spec.model_copy(
        update={
            "schedule": [_entry(e) for e in spec.schedule],
            "progressions": [_prog(p) for p in spec.progressions],
            "phases": phases,
            "new_routines": [],
        }
    )


def synthesize_routines(
    spec: ProgramSpec, ctx: MaterializeContext, exercise_meta: ExerciseMeta
) -> tuple[ProgramSpec, MaterializeContext]:
    """PREVIEW resolution: fold ``new_routines`` into the context as synthetic
    (negative-id) templates and rewrite refs, so ``materialize`` can expand them
    with no DB write. ``exercise_meta`` supplies each exercise's name + is_timed.
    Returns the (spec, ctx) unchanged when there are no new routines."""
    if not spec.new_routines:
        return spec, ctx
    key_to_id = {r.key: -(i + 1) for i, r in enumerate(spec.new_routines)}
    templates = dict(ctx.templates)
    for r in spec.new_routines:
        sid = key_to_id[r.key]
        templates[sid] = TemplateCtx(
            template_id=sid,
            name=r.name,
            exercises=[
                TemplateExerciseCtx(
                    exercise_id=e.exercise_id,
                    name=exercise_meta.get(e.exercise_id, (f"#{e.exercise_id}", False))[0],
                    is_timed=exercise_meta.get(e.exercise_id, ("", False))[1],
                    target_sets=e.sets,
                    target_reps=e.reps,
                    target_weight=e.weight,
                    target_duration_seconds=e.duration_seconds,
                    rest_seconds=e.rest_seconds,
                )
                for e in r.exercises
            ],
        )
    resolved = rewrite_routine_refs(spec, key_to_id)
    return resolved, MaterializeContext(templates=templates, weight_unit=ctx.weight_unit)


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
    objective_id: int | None = None  # which objective's block (season phase) this is
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
    progressions: list[ExerciseProgression], template_id: int, exercise_id: int
) -> ExerciseProgression | None:
    """Most specific matching progression: exercise-specific beats template-wide."""
    specific = None
    template_wide = None
    for p in progressions:
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
    """Expand a spec into one ``PlannedWorkoutData`` per (week, schedule entry),
    across every season block. Flat specs are a single block."""
    plate = PLATE_INCREMENT.get(ctx.weight_unit, PLATE_INCREMENT["lb"])
    out: list[PlannedWorkoutData] = []
    for block in program_blocks(spec):
        out += _materialize_block(block, ctx, plate)
    out.sort(key=lambda p: (p.scheduled_date, p.template_id or 0))
    return out


def _materialize_block(
    block: Block, ctx: MaterializeContext, plate: float
) -> list[PlannedWorkoutData]:
    out: list[PlannedWorkoutData] = []
    dw = block.duration_weeks

    for entry in block.schedule:
        tpl = ctx.templates.get(entry.template_id)
        if tpl is None:
            continue  # unknown template (grounding should prevent this) — skip, don't guess
        first_date = _first_on_or_after(block.start_date, _weekday_index(entry.weekday))

        for w in range(1, dw + 1):
            f = 0.0 if dw == 1 else (w - 1) / (dw - 1)
            deload = w in block.deload_weeks
            scheduled = first_date + timedelta(days=(w - 1) * 7)
            exercises: list[PlannedExerciseData] = []

            for i, te in enumerate(tpl.exercises):
                prog = _find_progression(block.progressions, entry.template_id, te.exercise_id)
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
                    objective_id=block.objective_id,
                    exercises=exercises,
                )
            )

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
    """Last scheduled date across all blocks (for Program.end_date)."""
    last = start_date_of(spec)
    for block in program_blocks(spec):
        for entry in block.schedule:
            first = _first_on_or_after(block.start_date, _weekday_index(entry.weekday))
            d = first + timedelta(days=(block.duration_weeks - 1) * 7)
            last = max(last, d)
    return last
