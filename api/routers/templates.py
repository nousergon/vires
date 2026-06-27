"""Workout templates ("Routines") — build a reusable routine, start workouts from it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import Exercise, TemplateExercise, WorkoutTemplate
from api.db.session import get_db
from api.schemas.template import (
    TemplateCreate,
    TemplateExerciseIn,
    TemplateExerciseOut,
    TemplateOut,
    TemplateSummary,
    TemplateUpdate,
)
from api.serializers import to_exercise_brief

router = APIRouter(prefix="/templates", tags=["templates"])


def to_template_out(tpl: WorkoutTemplate) -> TemplateOut:
    return TemplateOut(
        id=tpl.id,
        name=tpl.name,
        notes=tpl.notes,
        created_at=tpl.created_at,
        updated_at=tpl.updated_at,
        exercises=[
            TemplateExerciseOut(
                id=te.id,
                order_index=te.order_index,
                exercise=to_exercise_brief(te.exercise),
                target_sets=te.target_sets,
                target_reps=te.target_reps,
                rest_seconds=te.rest_seconds,
                notes=te.notes,
            )
            for te in tpl.exercises
        ],
    )


def _resolve_exercises(
    db: Session, items: list[TemplateExerciseIn], ident: Identity
) -> list[TemplateExercise]:
    """Validate every referenced exercise is visible, return ordered rows."""
    out: list[TemplateExercise] = []
    for idx, item in enumerate(items):
        ex = db.get(Exercise, item.exercise_id)
        if ex is None or (ex.tenant_id is not None and ex.tenant_id != ident.tenant_id):
            raise HTTPException(400, f"Unknown exercise_id {item.exercise_id}")
        out.append(
            TemplateExercise(
                exercise_id=item.exercise_id,
                order_index=idx,
                target_sets=item.target_sets,
                target_reps=item.target_reps,
                rest_seconds=item.rest_seconds,
                notes=item.notes,
            )
        )
    return out


def _get_owned(db: Session, template_id: int, ident: Identity) -> WorkoutTemplate:
    tpl = db.get(WorkoutTemplate, template_id)
    if tpl is None or tpl.tenant_id != ident.tenant_id or tpl.user_id != ident.user_id:
        raise HTTPException(404, "Template not found")
    return tpl


@router.get("", response_model=list[TemplateSummary])
def list_templates(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[TemplateSummary]:
    tpls = db.scalars(
        select(WorkoutTemplate)
        .where(
            WorkoutTemplate.tenant_id == ident.tenant_id,
            WorkoutTemplate.user_id == ident.user_id,
        )
        .order_by(WorkoutTemplate.updated_at.desc())
    ).all()
    return [
        TemplateSummary(
            id=t.id,
            name=t.name,
            notes=t.notes,
            exercise_count=len(t.exercises),
            updated_at=t.updated_at,
        )
        for t in tpls
    ]


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    body: TemplateCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> TemplateOut:
    tpl = WorkoutTemplate(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=body.name.strip(),
        notes=body.notes,
        exercises=_resolve_exercises(db, body.exercises, ident),
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return to_template_out(tpl)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> TemplateOut:
    return to_template_out(_get_owned(db, template_id, ident))


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    body: TemplateUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> TemplateOut:
    tpl = _get_owned(db, template_id, ident)
    if body.name is not None:
        tpl.name = body.name.strip()
    if body.notes is not None:
        tpl.notes = body.notes
    if body.exercises is not None:
        tpl.exercises = _resolve_exercises(db, body.exercises, ident)  # replaces (orphan-deleted)
    db.commit()
    db.refresh(tpl)
    return to_template_out(tpl)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_owned(db, template_id, ident))
    db.commit()
    return Response(status_code=204)
