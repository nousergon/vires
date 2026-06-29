"""Workout sessions: start (empty or from a template), log sets, finish, history."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import (
    PlannedWorkout,
    SessionExercise,
    SetEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from api.db.session import get_db
from api.schemas.exercise import ExercisePerformance, PerformedSet
from api.schemas.workout import (
    SessionExerciseIn,
    SessionExerciseOut,
    SessionExerciseUpdate,
    SetIn,
    SetOut,
    SetUpdate,
    WorkoutSessionOut,
    WorkoutStart,
    WorkoutSummary,
)
from api.serializers import to_exercise_brief

router = APIRouter(prefix="/workouts", tags=["workouts"])


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# serialization helpers
# --------------------------------------------------------------------------- #
def _set_out(s: SetEntry) -> SetOut:
    return SetOut(
        id=s.id,
        set_number=s.set_number,
        reps=s.reps,
        weight=s.weight,
        rpe=s.rpe,
        duration_seconds=s.duration_seconds,
        is_warmup=s.is_warmup,
        completed_at=s.completed_at,
    )


def _last_performance(
    db: Session, ident: Identity, exercise_id: int, exclude_session_id: int
) -> ExercisePerformance | None:
    """Most recent prior session (with logged sets) where the user did this exercise."""
    candidates = db.scalars(
        select(SessionExercise)
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .where(
            SessionExercise.exercise_id == exercise_id,
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.id != exclude_session_id,
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(10)
    ).all()
    for se in candidates:
        if se.sets:
            return ExercisePerformance(
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
    return None


def _se_out(db: Session, ident: Identity, se: SessionExercise) -> SessionExerciseOut:
    return SessionExerciseOut(
        id=se.id,
        order_index=se.order_index,
        exercise=to_exercise_brief(se.exercise),
        target_sets=se.target_sets,
        target_reps=se.target_reps,
        target_weight=se.target_weight,
        target_duration_seconds=se.target_duration_seconds,
        rest_seconds=se.rest_seconds,
        notes=se.notes,
        sets=[_set_out(s) for s in se.sets],
        previous_performance=_last_performance(db, ident, se.exercise_id, se.session_id),
    )


def _session_out(db: Session, ident: Identity, ws: WorkoutSession) -> WorkoutSessionOut:
    return WorkoutSessionOut(
        id=ws.id,
        name=ws.name,
        started_at=ws.started_at,
        ended_at=ws.ended_at,
        notes=ws.notes,
        template_id=ws.template_id,
        exercises=[_se_out(db, ident, se) for se in ws.exercises],
    )


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #
def _get_session(db: Session, session_id: int, ident: Identity) -> WorkoutSession:
    ws = db.get(WorkoutSession, session_id)
    if ws is None or ws.tenant_id != ident.tenant_id or ws.user_id != ident.user_id:
        raise HTTPException(404, "Workout not found")
    return ws


def _get_se(db: Session, ws: WorkoutSession, se_id: int) -> SessionExercise:
    se = db.get(SessionExercise, se_id)
    if se is None or se.session_id != ws.id:
        raise HTTPException(404, "Exercise not in this workout")
    return se


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
@router.post("", response_model=WorkoutSessionOut, status_code=201)
def start_workout(
    body: WorkoutStart,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    name = body.name
    exercises: list[SessionExercise] = []
    if body.template_id is not None:
        tpl = db.get(WorkoutTemplate, body.template_id)
        if tpl is None or tpl.tenant_id != ident.tenant_id or tpl.user_id != ident.user_id:
            raise HTTPException(404, "Template not found")
        name = name or tpl.name
        exercises = [
            SessionExercise(
                exercise_id=te.exercise_id,
                order_index=te.order_index,
                target_sets=te.target_sets,
                target_reps=te.target_reps,
                target_weight=te.target_weight,
                target_duration_seconds=te.target_duration_seconds,
                rest_seconds=te.rest_seconds,
                notes=te.notes,
            )
            for te in tpl.exercises
        ]
    ws = WorkoutSession(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=name,
        started_at=_now(),
        template_id=body.template_id,
        exercises=exercises,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    # Pre-create the planned set rows for template exercises (Strong-style: you
    # see N empty sets ready to fill, prefilled from last time / target reps).
    for se in ws.exercises:
        _seed_planned_sets(db, ident, se)
    db.commit()
    db.refresh(ws)
    return _session_out(db, ident, ws)


def _seed_planned_sets(db: Session, ident: Identity, se: SessionExercise) -> None:
    n = se.target_sets or 0
    if n <= 0 or se.sets:
        return
    prev = _last_performance(db, ident, se.exercise_id, se.session_id)
    prev_sets = prev.sets if prev else []
    for i in range(n):
        ghost = prev_sets[i] if i < len(prev_sets) else (prev_sets[-1] if prev_sets else None)
        # Prefer last time's ACTUAL logged weight; fall back to the routine's
        # target weight when there's no history or the prior weight was blank
        # (e.g. earlier planned sets that were never filled in).
        last_weight = ghost.weight if ghost else None
        timed = se.exercise.is_timed
        db.add(
            SetEntry(
                session_exercise_id=se.id,
                set_number=i + 1,
                reps=None if timed else ((ghost.reps if ghost else None) or se.target_reps),
                weight=last_weight if last_weight is not None else se.target_weight,
                # timed exercises seed the target hold; actual is logged on completion
                duration_seconds=se.target_duration_seconds if timed else None,
                completed_at=None,
            )
        )


@router.get("", response_model=list[WorkoutSummary])
def list_workouts(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[WorkoutSummary]:
    sessions = db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    out: list[WorkoutSummary] = []
    for ws in sessions:
        set_count = 0
        volume = 0.0
        for se in ws.exercises:
            for s in se.sets:
                set_count += 1
                if not s.is_warmup and s.reps and s.weight:
                    volume += s.reps * s.weight
        out.append(
            WorkoutSummary(
                id=ws.id,
                name=ws.name,
                started_at=ws.started_at,
                ended_at=ws.ended_at,
                exercise_count=len(ws.exercises),
                set_count=set_count,
                total_volume=round(volume, 2),
            )
        )
    return out


@router.get("/{session_id}", response_model=WorkoutSessionOut)
def get_workout(
    session_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    return _session_out(db, ident, _get_session(db, session_id, ident))


@router.post("/{session_id}/finish", response_model=WorkoutSessionOut)
def finish_workout(
    session_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    ws = _get_session(db, session_id, ident)
    if ws.ended_at is None:
        ws.ended_at = _now()
        db.commit()
        db.refresh(ws)
    return _session_out(db, ident, ws)


@router.delete("/{session_id}", status_code=204)
def delete_workout(
    session_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    ws = _get_session(db, session_id, ident)
    # A planned workout that this session fulfilled points back at it via
    # ``session_id`` (FK enforced). Detach the link and revert the planned day to
    # 'planned' before deleting — otherwise the delete violates the FK (500), and
    # the calendar should show the day as un-done once its log is gone.
    fulfilled = db.scalars(
        select(PlannedWorkout).where(PlannedWorkout.session_id == ws.id)
    ).all()
    for pw in fulfilled:
        pw.session_id = None
        if pw.status == "completed":
            pw.status = "planned"
    db.delete(ws)
    db.commit()
    return Response(status_code=204)


@router.post("/{session_id}/exercises", response_model=SessionExerciseOut, status_code=201)
def add_session_exercise(
    session_id: int,
    body: SessionExerciseIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SessionExerciseOut:
    from api.db.models import Exercise

    ws = _get_session(db, session_id, ident)
    ex = db.get(Exercise, body.exercise_id)
    if ex is None or (ex.tenant_id is not None and ex.tenant_id != ident.tenant_id):
        raise HTTPException(400, f"Unknown exercise_id {body.exercise_id}")
    next_order = max((se.order_index for se in ws.exercises), default=-1) + 1
    se = SessionExercise(
        session_id=ws.id,
        exercise_id=body.exercise_id,
        order_index=next_order,
        target_sets=body.target_sets,
        target_reps=body.target_reps,
        target_weight=body.target_weight,
        target_duration_seconds=body.target_duration_seconds,
        rest_seconds=body.rest_seconds,
        notes=body.notes,
    )
    db.add(se)
    db.commit()
    db.refresh(se)
    return _se_out(db, ident, se)


@router.patch("/{session_id}/exercises/{se_id}", response_model=SessionExerciseOut)
def update_session_exercise(
    session_id: int,
    se_id: int,
    body: SessionExerciseUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SessionExerciseOut:
    ws = _get_session(db, session_id, ident)
    se = _get_se(db, ws, se_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(se, field, value)
    db.commit()
    db.refresh(se)
    return _se_out(db, ident, se)


@router.delete("/{session_id}/exercises/{se_id}", status_code=204)
def remove_session_exercise(
    session_id: int,
    se_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    ws = _get_session(db, session_id, ident)
    db.delete(_get_se(db, ws, se_id))
    db.commit()
    return Response(status_code=204)


@router.post("/{session_id}/exercises/{se_id}/sets", response_model=SetOut, status_code=201)
def log_set(
    session_id: int,
    se_id: int,
    body: SetIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SetOut:
    ws = _get_session(db, session_id, ident)
    se = _get_se(db, ws, se_id)
    number = body.set_number or (max((s.set_number for s in se.sets), default=0) + 1)
    s = SetEntry(
        session_exercise_id=se.id,
        set_number=number,
        reps=body.reps,
        weight=body.weight,
        rpe=body.rpe,
        duration_seconds=body.duration_seconds,
        is_warmup=body.is_warmup,
        completed_at=_now() if body.done else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _set_out(s)


@router.patch("/{session_id}/exercises/{se_id}/sets/{set_id}", response_model=SetOut)
def update_set(
    session_id: int,
    se_id: int,
    set_id: int,
    body: SetUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SetOut:
    ws = _get_session(db, session_id, ident)
    se = _get_se(db, ws, se_id)
    s = db.get(SetEntry, set_id)
    if s is None or s.session_exercise_id != se.id:
        raise HTTPException(404, "Set not found")
    fields = body.model_dump(exclude_unset=True)
    done = fields.pop("done", None)
    if done is not None:
        s.completed_at = _now() if done else None
    for field, value in fields.items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return _set_out(s)


@router.delete("/{session_id}/exercises/{se_id}/sets/{set_id}", status_code=204)
def delete_set(
    session_id: int,
    se_id: int,
    set_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    ws = _get_session(db, session_id, ident)
    se = _get_se(db, ws, se_id)
    s = db.get(SetEntry, set_id)
    if s is None or s.session_exercise_id != se.id:
        raise HTTPException(404, "Set not found")
    db.delete(s)
    db.commit()
    return Response(status_code=204)
