"""Calendar + planned workouts.

The calendar unifies the past (logged ``WorkoutSession``s, by ``started_at``) and
the future (``PlannedWorkout``s, by ``scheduled_date``). Starting a planned
workout seeds a live session from its prescription and links the two.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import (
    Exercise,
    PlannedExercise,
    PlannedWorkout,
    Program,
    SessionExercise,
    SetEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from api.db.session import get_db
from api.routers.workouts import _session_out  # canonical session serializer
from api.schemas.plan import (
    CalendarEntry,
    PlannedWorkoutCreate,
    PlannedWorkoutOut,
    PlannedWorkoutUpdate,
    ProgramSummary,
)
from api.schemas.workout import WorkoutSessionOut
from api.serializers import to_planned_workout_out

router = APIRouter(prefix="/plan", tags=["plan"])

_VALID_STATUS = {"planned", "completed", "skipped"}


def _now() -> datetime:
    return datetime.now(UTC)


def _get_planned(db: Session, planned_id: int, ident: Identity) -> PlannedWorkout:
    pw = db.get(PlannedWorkout, planned_id)
    if pw is None or pw.tenant_id != ident.tenant_id or pw.user_id != ident.user_id:
        raise HTTPException(404, "Planned workout not found")
    return pw


def _get_program(db: Session, program_id: int, ident: Identity) -> Program:
    p = db.get(Program, program_id)
    if p is None or p.tenant_id != ident.tenant_id or p.user_id != ident.user_id:
        raise HTTPException(404, "Program not found")
    return p


# --------------------------------------------------------------------------- #
# calendar feed
# --------------------------------------------------------------------------- #
@router.get("/calendar", response_model=list[CalendarEntry])
def calendar(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[CalendarEntry]:
    if end < start:
        raise HTTPException(400, "end must be on or after start")
    lo = datetime.combine(start, time.min, tzinfo=UTC)
    hi = datetime.combine(end, time.max, tzinfo=UTC)

    entries: list[CalendarEntry] = []

    sessions = db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.started_at >= lo,
            WorkoutSession.started_at <= hi,
        )
        .order_by(WorkoutSession.started_at)
    ).all()
    for ws in sessions:
        entries.append(
            CalendarEntry(
                kind="session",
                date=ws.started_at.date(),
                id=ws.id,
                name=ws.name,
                status="completed" if ws.ended_at else "in_progress",
                template_id=ws.template_id,
                exercise_count=len(ws.exercises),
            )
        )

    planned = db.scalars(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.tenant_id == ident.tenant_id,
            PlannedWorkout.user_id == ident.user_id,
            PlannedWorkout.scheduled_date >= start,
            PlannedWorkout.scheduled_date <= end,
        )
        .order_by(PlannedWorkout.scheduled_date)
    ).all()
    for pw in planned:
        entries.append(
            CalendarEntry(
                kind="planned",
                date=pw.scheduled_date,
                id=pw.id,
                name=pw.name,
                status=pw.status,
                program_id=pw.program_id,
                template_id=pw.template_id,
                exercise_count=len(pw.exercises),
                session_id=pw.session_id,
            )
        )

    entries.sort(key=lambda e: (e.date, 0 if e.kind == "session" else 1))
    return entries


# --------------------------------------------------------------------------- #
# planned workout CRUD + start
# --------------------------------------------------------------------------- #
def _resolve_planned_exercises(
    db: Session, items, ident: Identity
) -> list[PlannedExercise]:
    out: list[PlannedExercise] = []
    for idx, item in enumerate(items):
        ex = db.get(Exercise, item.exercise_id)
        if ex is None or (ex.tenant_id is not None and ex.tenant_id != ident.tenant_id):
            raise HTTPException(400, f"Unknown exercise_id {item.exercise_id}")
        out.append(
            PlannedExercise(
                exercise_id=item.exercise_id,
                order_index=idx,
                target_sets=item.target_sets,
                target_reps=item.target_reps,
                target_weight=item.target_weight,
                target_duration_seconds=item.target_duration_seconds,
                rest_seconds=item.rest_seconds,
                notes=item.notes,
            )
        )
    return out


@router.post("/planned", response_model=PlannedWorkoutOut, status_code=201)
def create_planned(
    body: PlannedWorkoutCreate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> PlannedWorkoutOut:
    """Manually schedule one workout (optionally seeded from a routine)."""
    name = body.name
    exercises: list[PlannedExercise] = []
    if body.template_id is not None:
        tpl = db.get(WorkoutTemplate, body.template_id)
        if tpl is None or tpl.tenant_id != ident.tenant_id or tpl.user_id != ident.user_id:
            raise HTTPException(404, "Template not found")
        name = name or tpl.name
        exercises = [
            PlannedExercise(
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
    pw = PlannedWorkout(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        template_id=body.template_id,
        scheduled_date=body.scheduled_date,
        name=name or "Workout",
        notes=body.notes,
        status="planned",
        created_by="user",
        exercises=exercises,
    )
    db.add(pw)
    db.commit()
    db.refresh(pw)
    return to_planned_workout_out(pw)


@router.get("/planned/{planned_id}", response_model=PlannedWorkoutOut)
def get_planned(
    planned_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> PlannedWorkoutOut:
    return to_planned_workout_out(_get_planned(db, planned_id, ident))


@router.patch("/planned/{planned_id}", response_model=PlannedWorkoutOut)
def update_planned(
    planned_id: int,
    body: PlannedWorkoutUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> PlannedWorkoutOut:
    pw = _get_planned(db, planned_id, ident)
    if body.scheduled_date is not None:
        pw.scheduled_date = body.scheduled_date
    if body.name is not None:
        pw.name = body.name.strip()
    if body.notes is not None:
        pw.notes = body.notes
    if body.status is not None:
        if body.status not in _VALID_STATUS:
            raise HTTPException(400, f"status must be one of {sorted(_VALID_STATUS)}")
        pw.status = body.status
    if body.exercises is not None:
        pw.exercises = _resolve_planned_exercises(db, body.exercises, ident)
    db.commit()
    db.refresh(pw)
    return to_planned_workout_out(pw)


@router.delete("/planned/{planned_id}", status_code=204)
def delete_planned(
    planned_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_planned(db, planned_id, ident))
    db.commit()
    return Response(status_code=204)


@router.post("/planned/{planned_id}/start", response_model=WorkoutSessionOut, status_code=201)
def start_planned(
    planned_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Seed a live session from the planned prescription; link + mark completed."""
    pw = _get_planned(db, planned_id, ident)

    # Idempotent: if already started, return the existing session.
    if pw.session_id is not None:
        existing = db.get(WorkoutSession, pw.session_id)
        if existing is not None:
            return _session_out(db, ident, existing)

    ws = WorkoutSession(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=pw.name,
        started_at=_now(),
        template_id=pw.template_id,
        planned_workout_id=pw.id,
        exercises=[
            SessionExercise(
                exercise_id=pe.exercise_id,
                order_index=pe.order_index,
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
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # Pre-create planned set rows straight from the coach's prescription (NOT
    # last-performance — the prescription already encodes this week's progression).
    for se in ws.exercises:
        n = se.target_sets or 0
        if n <= 0 or se.sets:
            continue
        timed = se.exercise.is_timed
        for i in range(n):
            db.add(
                SetEntry(
                    session_exercise_id=se.id,
                    set_number=i + 1,
                    reps=None if timed else se.target_reps,
                    weight=None if timed else se.target_weight,
                    duration_seconds=se.target_duration_seconds if timed else None,
                    completed_at=None,
                )
            )

    pw.status = "completed"
    pw.session_id = ws.id
    db.commit()
    db.refresh(ws)
    return _session_out(db, ident, ws)


# --------------------------------------------------------------------------- #
# programs
# --------------------------------------------------------------------------- #
@router.get("/programs", response_model=list[ProgramSummary])
def list_programs(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[ProgramSummary]:
    programs = db.scalars(
        select(Program)
        .where(Program.tenant_id == ident.tenant_id, Program.user_id == ident.user_id)
        .order_by(Program.created_at.desc())
    ).all()
    out: list[ProgramSummary] = []
    for p in programs:
        completed = sum(1 for pw in p.planned_workouts if pw.status == "completed")
        out.append(
            ProgramSummary(
                id=p.id,
                name=p.name,
                goal_text=p.goal_text,
                start_date=p.start_date,
                end_date=p.end_date,
                status=p.status,
                planned_count=len(p.planned_workouts),
                completed_count=completed,
            )
        )
    return out


@router.delete("/programs/{program_id}", status_code=204)
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    db.delete(_get_program(db, program_id, ident))
    db.commit()
    return Response(status_code=204)
