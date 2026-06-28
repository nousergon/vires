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
    SessionExercise,
    SetEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
)


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
