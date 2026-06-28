"""AI coach: generate a multi-week program from a natural-language request.

``POST /coach/generate`` runs the LLM (grounded, forced tool-use) -> validated
``ProgramSpec`` -> deterministic materialization, and returns a NON-persisted
preview. ``POST /coach/programs`` re-materializes the confirmed spec server-side
(single source of truth) and persists it. Refine = resend ``prior_spec``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import PlannedExercise, PlannedWorkout, Program
from api.db.session import get_db
from api.schemas.coach import (
    GenerateRequest,
    PlannedExercisePreview,
    PlannedWorkoutPreview,
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
    workouts = materialize(spec, ctx)
    if not workouts:
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
        planned_workouts=[
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
            for pw in workouts
        ],
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return to_program_out(program)
