"""ORM -> Pydantic serializers shared across routers."""

from __future__ import annotations

from api.db.models import Exercise, PlannedWorkout, Program
from api.schemas.exercise import ExerciseBrief, ExerciseOut
from api.schemas.plan import (
    PlannedExerciseOut,
    PlannedWorkoutOut,
    ProgramOut,
)


def dumbbell_seed_weight(total_weight: float | None, equipment: str | None) -> float | None:
    """A programmed/target weight is authored as the bilateral TOTAL (e.g. "90
    lbs" for a pair of 45s); the live per-set weight a user actually logs is
    per-hand. Halve at the one boundary where a total-denominated target
    (``TemplateExercise``/``PlannedExercise.target_weight``) becomes a live
    ``SessionExercise``/``SetEntry`` value — every downstream consumer
    (records, autoregulation, "last time" hints) then reads a self-consistent
    per-hand number with no further conversion needed."""
    if total_weight is None or equipment != "dumbbell":
        return total_weight
    return total_weight / 2


def to_exercise_out(ex: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=ex.id,
        name=ex.name,
        primary_muscles=ex.primary_muscles or [],
        secondary_muscles=ex.secondary_muscles or [],
        equipment=ex.equipment,
        mechanic=ex.mechanic,
        category=ex.category,
        movement_pattern=ex.movement_pattern,
        description=ex.description,
        provenance=ex.provenance,
        is_timed=ex.is_timed,
        aliases=[a.alias_text for a in ex.aliases],
    )


def to_exercise_brief(ex: Exercise) -> ExerciseBrief:
    return ExerciseBrief(
        id=ex.id,
        name=ex.name,
        primary_muscles=ex.primary_muscles or [],
        equipment=ex.equipment,
        is_timed=ex.is_timed,
        movement_pattern=ex.movement_pattern,
    )


def to_planned_workout_out(pw: PlannedWorkout) -> PlannedWorkoutOut:
    return PlannedWorkoutOut(
        id=pw.id,
        program_id=pw.program_id,
        template_id=pw.template_id,
        objective_id=pw.objective_id,
        scheduled_date=pw.scheduled_date,
        rescheduled_from=pw.rescheduled_from,
        name=pw.name,
        notes=pw.notes,
        week_index=pw.week_index,
        status=pw.status,
        created_by=pw.created_by,
        session_id=pw.session_id,
        exercises=[
            PlannedExerciseOut(
                id=pe.id,
                order_index=pe.order_index,
                exercise=to_exercise_brief(pe.exercise),
                target_sets=pe.target_sets,
                target_reps=pe.target_reps,
                target_weight=pe.target_weight,
                target_duration_seconds=pe.target_duration_seconds,
                rest_seconds=pe.rest_seconds,
                notes=pe.notes,
            )
            for pe in pw.exercises
        ],
    )


def program_coach_summary(program: Program) -> str | None:
    """The coach's strategy narrative, lifted from the stored spec."""
    if isinstance(program.spec, dict):
        text = program.spec.get("coach_summary")
        return text or None
    return None


def to_program_out(program: Program) -> ProgramOut:
    return ProgramOut(
        id=program.id,
        name=program.name,
        notes=program.notes,
        goal_text=program.goal_text,
        coach_summary=program_coach_summary(program),
        objective_id=program.objective_id,
        start_date=program.start_date,
        end_date=program.end_date,
        status=program.status,
        created_at=program.created_at,
        planned_workouts=[to_planned_workout_out(pw) for pw in program.planned_workouts],
    )
