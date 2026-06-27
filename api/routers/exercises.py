"""Exercise catalog: hybrid search, create-with-dedup, aliases, history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.db.fts import fts_sync_exercise
from api.db.identity import Identity, current_identity
from api.db.models import Exercise, ExerciseAlias, SessionExercise, WorkoutSession
from api.db.seed import normalize_name
from api.db.session import get_db
from api.schemas.exercise import (
    AliasCreate,
    ExerciseCreate,
    ExerciseCreateResult,
    ExerciseOut,
    ExercisePerformance,
    ExerciseSearchOut,
    PerformedSet,
)
from api.services.search import get_search_service

router = APIRouter(prefix="/exercises", tags=["exercises"])


def to_out(ex: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=ex.id,
        name=ex.name,
        primary_muscles=ex.primary_muscles or [],
        secondary_muscles=ex.secondary_muscles or [],
        equipment=ex.equipment,
        mechanic=ex.mechanic,
        category=ex.category,
        description=ex.description,
        provenance=ex.provenance,
        aliases=[a.alias_text for a in ex.aliases],
    )


def _visible(ex: Exercise | None, ident: Identity) -> bool:
    return ex is not None and (ex.tenant_id is None or ex.tenant_id == ident.tenant_id)


@router.get("/search", response_model=list[ExerciseSearchOut])
def search_exercises(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[ExerciseSearchOut]:
    hits = get_search_service().search(db, q, tenant_id=ident.tenant_id, limit=limit)
    return [ExerciseSearchOut(exercise=to_out(h.exercise), score=h.score) for h in hits]


@router.post("", response_model=ExerciseCreateResult)
def create_exercise(
    body: ExerciseCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ExerciseCreateResult:
    name = body.name.strip()
    cn = normalize_name(name)

    if not body.force:
        # 1) exact normalized-name match (definite duplicate)
        exact = db.scalar(
            select(Exercise).where(
                Exercise.canonical_name == cn,
                Exercise.canonical_exercise_id.is_(None),
                or_(Exercise.tenant_id.is_(None), Exercise.tenant_id == ident.tenant_id),
            )
        )
        if exact is not None:
            return ExerciseCreateResult(
                created=False, reason="exact", duplicate_of=to_out(exact)
            )
        # 2) advisory semantic near-duplicate
        dup = get_search_service().find_duplicate(name)
        if dup is not None:
            cand = db.get(Exercise, dup[0])
            if _visible(cand, ident) and cand.canonical_exercise_id is None:
                return ExerciseCreateResult(
                    created=False,
                    reason="similar",
                    duplicate_of=to_out(cand),
                    similarity=round(dup[1], 4),
                )

    ex = Exercise(
        tenant_id=ident.tenant_id,
        name=name,
        canonical_name=cn,
        primary_muscles=body.primary_muscles,
        secondary_muscles=body.secondary_muscles,
        equipment=body.equipment,
        mechanic=body.mechanic,
        category=body.category,
        description=body.description,
        provenance="user",
        created_by_user_id=ident.user_id,
    )
    db.add(ex)
    db.flush()
    fts_sync_exercise(db, ex)
    db.commit()
    get_search_service().index_exercise(ex)
    return ExerciseCreateResult(created=True, reason="created", exercise=to_out(ex))


@router.get("/{exercise_id}", response_model=ExerciseOut)
def get_exercise(
    exercise_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ExerciseOut:
    ex = db.get(Exercise, exercise_id)
    if not _visible(ex, ident):
        raise HTTPException(404, "Exercise not found")
    return to_out(ex)


@router.post("/{exercise_id}/aliases", response_model=ExerciseOut)
def add_alias(
    exercise_id: int,
    body: AliasCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> ExerciseOut:
    ex = db.get(Exercise, exercise_id)
    if not _visible(ex, ident):
        raise HTTPException(404, "Exercise not found")
    alias = body.alias_text.strip()
    if alias and alias.lower() not in {a.alias_text.lower() for a in ex.aliases}:
        ex.aliases.append(ExerciseAlias(alias_text=alias))
        db.flush()
        fts_sync_exercise(db, ex)  # aliases feed BM25 keywords
        db.commit()
    return to_out(ex)


@router.get("/{exercise_id}/history", response_model=list[ExercisePerformance])
def exercise_history(
    exercise_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[ExercisePerformance]:
    """Past performances of an exercise for the current user, newest first.
    The first element powers the 'previous performance' hint while logging."""
    rows = db.scalars(
        select(SessionExercise)
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .where(
            SessionExercise.exercise_id == exercise_id,
            WorkoutSession.user_id == ident.user_id,
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(limit)
    ).all()
    out: list[ExercisePerformance] = []
    for se in rows:
        out.append(
            ExercisePerformance(
                session_id=se.session_id,
                session_name=se.session.name,
                date=se.session.started_at,
                sets=[
                    PerformedSet(
                        set_number=s.set_number,
                        reps=s.reps,
                        weight=s.weight,
                        rpe=s.rpe,
                        is_warmup=s.is_warmup,
                    )
                    for s in se.sets
                ],
            )
        )
    return out
