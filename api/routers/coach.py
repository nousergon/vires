"""AI coach: generate a multi-week program from a natural-language request.

``POST /coach/generate`` runs the LLM (grounded, forced tool-use) -> validated
``ProgramSpec`` -> deterministic materialization, and returns a NON-persisted
preview. ``POST /coach/programs`` re-materializes the confirmed spec server-side
(single source of truth) and persists it. Refine = resend ``prior_spec``.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import PlannedExercise, PlannedWorkout, Program
from api.db.session import get_db
from api.schemas.coach import (
    GenerateRequest,
    ModifyRequest,
    PlannedExercisePreview,
    PlannedWorkoutPreview,
    ProgramModifyPreview,
    ProgramPreview,
    ProgramSpec,
    SaveProgramRequest,
)
from api.schemas.plan import ProgramOut
from api.serializers import to_program_out
from api.services.coach.agent import CoachError, CoachUnavailable, generate_spec
from api.services.coach.context import build_materialize_context
from api.services.coach.materialize import (
    MaterializeContext,
    end_date,
    materialize,
)

router = APIRouter(prefix="/coach", tags=["coach"])


def _build_preview(spec: ProgramSpec, ctx: MaterializeContext) -> ProgramPreview:
    workouts = materialize(spec, ctx)
    return ProgramPreview(
        name=spec.name,
        coach_summary=spec.coach_summary,
        start_date=spec.start_date,
        end_date=end_date(spec),
        weight_unit=ctx.weight_unit,
        spec=spec,
        planned_workouts=[
            PlannedWorkoutPreview(
                template_id=pw.template_id,
                scheduled_date=pw.scheduled_date,
                name=pw.name,
                week_index=pw.week_index,
                exercises=[
                    PlannedExercisePreview(
                        exercise_id=e.exercise_id,
                        exercise_name=e.exercise_name,
                        order_index=e.order_index,
                        target_sets=e.target_sets,
                        target_reps=e.target_reps,
                        target_weight=e.target_weight,
                        target_duration_seconds=e.target_duration_seconds,
                        rest_seconds=e.rest_seconds,
                        notes=e.notes,
                    )
                    for e in pw.exercises
                ],
            )
            for pw in workouts
        ],
    )


@router.post("/generate", response_model=ProgramPreview)
def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramPreview:
    ctx = build_materialize_context(db, ident)
    if not ctx.templates:
        raise HTTPException(400, "Create at least one routine before asking the coach.")
    try:
        spec = generate_spec(body.message, ctx, date.today(), body.prior_spec)
    except CoachUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except CoachError as e:
        raise HTTPException(502, f"Coach could not build a plan: {e}") from e
    return _build_preview(spec, ctx)


@router.post("/programs", response_model=ProgramOut, status_code=201)
def save_program(
    body: SaveProgramRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramOut:
    ctx = build_materialize_context(db, ident)
    spec = body.spec
    rows = _materialize_rows(spec, ctx, ident)
    if not rows:
        raise HTTPException(400, "Spec produced no workouts (unknown templates?).")

    program = Program(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=(body.name or spec.name).strip(),
        goal_text=body.goal_text,
        spec=spec.model_dump(mode="json"),
        start_date=spec.start_date,
        end_date=end_date(spec),
        status="active",
        planned_workouts=rows,
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return to_program_out(program)


# --------------------------------------------------------------------------- #
# modification (reschedule / regenerate an existing program)
# --------------------------------------------------------------------------- #
def _materialize_rows(
    spec: ProgramSpec,
    ctx: MaterializeContext,
    ident: Identity,
    since: date | None = None,
) -> list[PlannedWorkout]:
    """Materialize the spec into PlannedWorkout ORM rows (optionally only on/after
    ``since`` — used when applying a modification to preserve completed history)."""
    rows: list[PlannedWorkout] = []
    for pw in materialize(spec, ctx):
        if since is not None and pw.scheduled_date < since:
            continue
        rows.append(
            PlannedWorkout(
                tenant_id=ident.tenant_id,
                user_id=ident.user_id,
                template_id=pw.template_id,
                scheduled_date=pw.scheduled_date,
                name=pw.name,
                week_index=pw.week_index,
                status="planned",
                created_by="coach",
                exercises=[
                    PlannedExercise(
                        exercise_id=e.exercise_id,
                        order_index=e.order_index,
                        target_sets=e.target_sets,
                        target_reps=e.target_reps,
                        target_weight=e.target_weight,
                        target_duration_seconds=e.target_duration_seconds,
                        rest_seconds=e.rest_seconds,
                        notes=e.notes,
                    )
                    for e in pw.exercises
                ],
            )
        )
    return rows


def _get_owned_program(db: Session, program_id: int, ident: Identity) -> Program:
    p = db.get(Program, program_id)
    if p is None or p.tenant_id != ident.tenant_id or p.user_id != ident.user_id:
        raise HTTPException(404, "Program not found")
    return p


def _program_spec(program: Program) -> ProgramSpec:
    if not program.spec:
        raise HTTPException(400, "This program has no editable coach spec.")
    return ProgramSpec.model_validate(program.spec)


def _cutover(program: Program, today: date) -> date:
    """First date a re-plan may occupy: today, or the day after the last completed
    workout — so applying a change never duplicates a day already trained."""
    completed = [pw.scheduled_date for pw in program.planned_workouts if pw.status == "completed"]
    return max([today, *(d + timedelta(days=1) for d in completed)])


@router.post("/programs/{program_id}/modify", response_model=ProgramModifyPreview)
def modify_program(
    program_id: int,
    body: ModifyRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramModifyPreview:
    """Preview a NL change to a program. The coach edits the stored spec (refine
    against prior_spec); nothing is persisted until PUT /coach/programs/{id}."""
    program = _get_owned_program(db, program_id, ident)
    prior = _program_spec(program)
    ctx = build_materialize_context(db, ident)
    try:
        new_spec = generate_spec(body.message, ctx, date.today(), prior_spec=prior)
    except CoachUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except CoachError as e:
        raise HTTPException(502, f"Coach could not modify the plan: {e}") from e

    cutover = _cutover(program, date.today())
    completed = sum(1 for pw in program.planned_workouts if pw.status == "completed")
    future = sum(1 for pw in materialize(new_spec, ctx) if pw.scheduled_date >= cutover)
    return ProgramModifyPreview(
        program_id=program.id,
        preview=_build_preview(new_spec, ctx),
        completed_preserved=completed,
        future_count=future,
    )


@router.put("/programs/{program_id}", response_model=ProgramOut)
def apply_program(
    program_id: int,
    body: SaveProgramRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ProgramOut:
    """Apply a (modified) spec: freeze completed workouts, replace every future
    (not-yet-done) one with the new materialization from today onward."""
    program = _get_owned_program(db, program_id, ident)
    ctx = build_materialize_context(db, ident)
    spec = body.spec
    cutover = _cutover(program, date.today())

    # Keep completed history; everything else (planned/skipped) is replaced from
    # the cutover forward (never re-adding an already-trained day).
    kept = [pw for pw in program.planned_workouts if pw.status == "completed"]
    new_future = _materialize_rows(spec, ctx, ident, since=cutover)
    program.planned_workouts = kept + new_future  # delete-orphan drops the rest

    program.spec = spec.model_dump(mode="json")
    if body.name:
        program.name = body.name.strip()
    program.start_date = spec.start_date
    program.end_date = end_date(spec)
    db.commit()
    db.refresh(program)
    return to_program_out(program)
