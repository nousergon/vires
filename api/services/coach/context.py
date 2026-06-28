"""Build the coach's grounding/materialization context from the database.

Kept here (not in the pure ``materialize`` module) so the materializer stays
DB-free and unit-testable. This is the one place that reads the user's routines
and recent performance into the dataclasses the coach + materializer consume.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, get_or_create_settings
from api.db.models import (
    Constraint,
    Exercise,
    Objective,
    SessionExercise,
    SetEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from api.services.coach.materialize import (
    ExerciseMeta,
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
)
from api.services.coach.objective_context import (
    CoachObjectiveContext,
    ConstraintCtx,
    ExerciseCandidate,
    ObjectiveCtx,
)
from api.services.search import get_search_service

# Cap the candidate pool so the grounding context stays compact.
_MAX_CANDIDATES = 60
_HITS_PER_TERM = 4


def _last_logged_weights(db: Session, ident: Identity) -> dict[int, float]:
    """Most recent non-warmup logged weight per exercise_id, for this user."""
    rows = db.execute(
        select(
            SessionExercise.exercise_id,
            SetEntry.weight,
            WorkoutSession.started_at,
        )
        .join(SetEntry, SetEntry.session_exercise_id == SessionExercise.id)
        .join(WorkoutSession, WorkoutSession.id == SessionExercise.session_id)
        .where(
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.tenant_id == ident.tenant_id,
            SetEntry.weight.is_not(None),
            SetEntry.is_warmup.is_(False),
        )
        .order_by(WorkoutSession.started_at.desc())
    ).all()
    last: dict[int, float] = {}
    for exercise_id, weight, _started in rows:
        last.setdefault(exercise_id, weight)  # first seen = most recent
    return last


def build_materialize_context(db: Session, ident: Identity) -> MaterializeContext:
    last_weights = _last_logged_weights(db, ident)
    templates: dict[int, TemplateCtx] = {}
    tpls = db.scalars(
        select(WorkoutTemplate).where(
            WorkoutTemplate.tenant_id == ident.tenant_id,
            WorkoutTemplate.user_id == ident.user_id,
        )
    ).all()
    for tpl in tpls:
        templates[tpl.id] = TemplateCtx(
            template_id=tpl.id,
            name=tpl.name,
            exercises=[
                TemplateExerciseCtx(
                    exercise_id=te.exercise_id,
                    name=te.exercise.name,
                    is_timed=te.exercise.is_timed,
                    target_sets=te.target_sets,
                    target_reps=te.target_reps,
                    target_weight=te.target_weight,
                    target_duration_seconds=te.target_duration_seconds,
                    rest_seconds=te.rest_seconds,
                    last_weight=last_weights.get(te.exercise_id),
                )
                for te in tpl.exercises
            ],
        )
    unit = get_or_create_settings(db, ident).weight_unit
    return MaterializeContext(templates=templates, weight_unit=unit)


def build_coach_objective_context(
    db: Session, ident: Identity
) -> CoachObjectiveContext:
    """The active primary objective + active constraints generation runs against.

    Empty (no objective, no constraints) for users who haven't set one — the
    coach then behaves exactly as before (generic routine-driven generation)."""
    objective = db.scalar(
        select(Objective).where(
            Objective.tenant_id == ident.tenant_id,
            Objective.user_id == ident.user_id,
            Objective.is_primary.is_(True),
        )
    )
    obj_ctx = (
        ObjectiveCtx(
            name=objective.name,
            kind=objective.kind,
            target_date=objective.target_date,
            sport=objective.sport,
            demands_profile=objective.demands_profile,
        )
        if objective is not None
        else None
    )
    constraints = db.scalars(
        select(Constraint)
        .where(
            Constraint.tenant_id == ident.tenant_id,
            Constraint.user_id == ident.user_id,
            Constraint.is_active.is_(True),
        )
        .order_by(Constraint.created_at)
    ).all()
    con_ctxs = [
        ConstraintCtx(
            kind=c.kind,
            label=c.label,
            directives=c.directives,
            defer_to_professional=c.defer_to_professional,
        )
        for c in constraints
    ]
    candidates = _build_exercise_candidates(db, ident, obj_ctx)
    return CoachObjectiveContext(
        objective=obj_ctx, constraints=con_ctxs, candidates=candidates
    )


def _build_exercise_candidates(
    db: Session, ident: Identity, obj_ctx: ObjectiveCtx | None
) -> list[ExerciseCandidate]:
    """Assemble the catalog exercise pool the coach may AUTHOR routines from,
    driven by the objective's needs-analysis ``search_terms``. Empty when there
    is no objective profile (then the coach only schedules existing routines)."""
    if obj_ctx is None or not obj_ctx.demands_profile:
        return []
    terms = obj_ctx.demands_profile.get("search_terms") or []
    if not terms:
        return []
    svc = get_search_service()
    out: dict[int, ExerciseCandidate] = {}
    for term in terms:
        for hit in svc.search(db, term, tenant_id=ident.tenant_id, limit=_HITS_PER_TERM):
            ex = hit.exercise
            if ex.id in out:
                continue
            out[ex.id] = ExerciseCandidate(
                exercise_id=ex.id,
                name=ex.name,
                is_timed=ex.is_timed,
                primary_muscles=list(ex.primary_muscles or []),
                equipment=ex.equipment,
            )
            if len(out) >= _MAX_CANDIDATES:
                return list(out.values())
    return list(out.values())


def exercise_meta_for_ids(db: Session, ids: set[int]) -> ExerciseMeta:
    """name + is_timed for each exercise id (for materializing authored routines)."""
    if not ids:
        return {}
    rows = db.scalars(select(Exercise).where(Exercise.id.in_(ids))).all()
    return {ex.id: (ex.name, ex.is_timed) for ex in rows}
