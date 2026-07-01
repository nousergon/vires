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
from api.serializers import to_exercise_out as to_out
from api.services.search import get_search_service

router = APIRouter(prefix="/exercises", tags=["exercises"])


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

    # Only BLOCK on an EXACT normalized-name match (precise, prevents literal
    # re-adds). A semantic "did you mean?" block was tried and removed: with
    # keyword-diluted embeddings it produced confident false positives (e.g.
    # "lunge dumbbell overhead" -> "Incline Dumbbell Flyes" @ 0.85), blocking
    # legitimate on-the-spot additions. The name-only hint below replaces it —
    # advisory only, never gates the create.
    if not body.force:
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

    # Non-blocking "similar exercise" hint on the higher-precision name-only
    # index, checked BEFORE this exercise is indexed (so it can't match itself).
    search_service = get_search_service()
    hint = search_service.find_similar_hint(name)
    similar_to = None
    similarity = None
    if hint is not None:
        hint_id, hint_similarity = hint
        candidate = db.get(Exercise, hint_id)
        if _visible(candidate, ident):
            similar_to = to_out(candidate)
            similarity = hint_similarity

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
    search_service.index_exercise(ex)
    return ExerciseCreateResult(
        created=True,
        reason="created",
        exercise=to_out(ex),
        similar_to=similar_to,
        similar_to_similarity=similarity,
    )


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
