"""Calendar + planned workouts.

The calendar unifies the past (logged ``WorkoutSession``s, by ``started_at``) and
the future (``PlannedWorkout``s, by ``scheduled_date``). Starting a planned
workout seeds a live session from its prescription and links the two.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity, get_or_create_settings
from api.db.models import (
    ActivityDetail,
    Exercise,
    Objective,
    PlannedExercise,
    PlannedWorkout,
    Program,
    SessionExercise,
    SetEntry,
    UserSettings,
    WorkoutSession,
    WorkoutTemplate,
)
from api.db.session import get_db
from api.routers.workouts import _session_out  # canonical session serializer
from api.schemas.plan import (
    CalendarEntry,
    FeedUrl,
    PlannedWorkoutCreate,
    PlannedWorkoutOut,
    PlannedWorkoutUpdate,
    ProgramSummary,
)
from api.schemas.workout import WorkoutSessionOut
from api.serializers import program_coach_summary, to_planned_workout_out
from api.services.ailments import load_open_ailments
from api.services.coach.ailment_gate import (
    AilmentFlag,
    ExerciseGateInput,
    blocking_flags,
    gate_exercise,
    relevant_ailment_flags,
)
from api.services.ics import IcsEvent, build_calendar
from api.services.recurrence import expand_occurrences
from api.services.reschedule import reschedule_missed

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


def _objective_name_map(db: Session, ident: Identity) -> dict[int, str]:
    """{objective_id: name} for this user — labels a planned day's training block."""
    rows = db.execute(
        select(Objective.id, Objective.name).where(
            Objective.tenant_id == ident.tenant_id,
            Objective.user_id == ident.user_id,
        )
    ).all()
    return {oid: name for oid, name in rows}


def _days_clipped(span_start: date, span_end: date, lo: date, hi: date) -> list[date]:
    """Each day in ``[span_start, span_end]`` that also falls within ``[lo, hi]``
    (inclusive), in order. Empty when the span doesn't intersect the window — the
    chokepoint that keeps multi-week objective bands bounded to the visible grid."""
    a, b = max(span_start, lo), min(span_end, hi)
    if b < a:
        return []
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


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
    now = _now()
    # Live status per emitted session — a fulfilled PlannedWorkout's own status
    # can't be trusted for display (start_planned marks it 'completed' at START
    # time), so the planned entry below takes its linked session's status and
    # the session's standalone entry is suppressed (one workout, one entry).
    session_status: dict[int, str] = {}
    for ws in sessions:
        if ws.ended_at is not None:
            status = "completed"
        elif ws.started_at > now:
            status = "upcoming"
        else:
            status = "in_progress"
        session_status[ws.id] = status
        entries.append(
            CalendarEntry(
                kind="session",
                date=ws.started_at.date(),
                id=ws.id,
                name=ws.name,
                status=status,
                template_id=ws.template_id,
                exercise_count=len(ws.exercises),
                session_type=ws.session_type,
            )
        )

    # Virtual occurrences of recurring ('weekly') activities — the athletic-
    # calendar merge (formerly a separate /calendar-events/window endpoint).
    # Unbounded by [lo, hi]: a template anchored months ago must still expand
    # into this window's occurrences. Every recurring template's own anchor
    # date, and every occurrence already materialized into its own linked row
    # (WorkoutSession.recurrence_source_id), is already covered by the
    # `sessions` query above — skip those dates here to avoid double-emitting.
    recurring = db.scalars(
        select(WorkoutSession)
        .join(ActivityDetail, ActivityDetail.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.session_type == "activity",
            ActivityDetail.recurrence == "weekly",
        )
    ).all()
    for template in recurring:
        materialized_dates = set(
            db.scalars(
                select(WorkoutSession.started_at).where(
                    WorkoutSession.recurrence_source_id == template.id,
                    WorkoutSession.started_at >= lo,
                    WorkoutSession.started_at <= hi,
                )
            ).all()
        )
        materialized_dates = {d.date() for d in materialized_dates}
        for occ_date, _occ_end in expand_occurrences(
            template.started_at.date(), None, "weekly", start, end
        ):
            if occ_date == template.started_at.date() or occ_date in materialized_dates:
                continue
            entries.append(
                CalendarEntry(
                    kind="session",
                    date=occ_date,
                    id=template.id,
                    name=template.name,
                    status="upcoming",
                    session_type="activity",
                    virtual=True,
                )
            )

    objective_names = _objective_name_map(db, ident)
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
    fulfilled_session_ids: set[int] = set()
    for pw in planned:
        # A planned day that's been fulfilled by a session is shown on the day
        # the session actually happened, not its original scheduled_date — so
        # doing Thursday's workout on Friday marks Friday and clears Thursday.
        # scheduled_date itself is left untouched (it's load-bearing for the
        # coach's week grid / replan cutover); only the calendar marker moves.
        entry_date = pw.scheduled_date
        entry_status = pw.status
        if pw.session_id is not None:
            linked = db.get(WorkoutSession, pw.session_id)
            if linked is not None:
                entry_date = linked.started_at.date()
            # One physical workout must render as ONE entry. The planned row
            # (prescription + objective linkage) absorbs its linked session,
            # taking the session's LIVE status — pw.status says 'completed'
            # from the moment start_planned runs, even mid-workout — and the
            # session's standalone entry is dropped below.
            if pw.session_id in session_status:
                entry_status = session_status[pw.session_id]
                fulfilled_session_ids.add(pw.session_id)
        entries.append(
            CalendarEntry(
                kind="planned",
                date=entry_date,
                id=pw.id,
                name=pw.name,
                status=entry_status,
                program_id=pw.program_id,
                template_id=pw.template_id,
                objective_id=pw.objective_id,
                objective_name=objective_names.get(pw.objective_id),
                exercise_count=len(pw.exercises),
                session_id=pw.session_id,
                rescheduled_from=pw.rescheduled_from,
            )
        )
    if fulfilled_session_ids:
        entries = [
            e
            for e in entries
            if not (e.kind == "session" and not e.virtual and e.id in fulfilled_session_ids)
        ]

    # Dated objectives as their OWN events — in-app parity with the ICS feed:
    # a peak marker on target_date (a multi-day band across event_end_date), and a
    # training-block band over the prep span (the days with attributed planned
    # work). Per-day, clipped to [start, end] so multi-week bands stay bounded.
    objectives = db.scalars(
        select(Objective).where(
            Objective.tenant_id == ident.tenant_id,
            Objective.user_id == ident.user_id,
            Objective.kind == "dated",
            Objective.target_date.is_not(None),
        )
    ).all()
    # True block span per objective = first..last attributed planned day (over ALL
    # of the user's planned work, not just the window — so a band that started
    # earlier still renders correctly at the window edge).
    block_rows = db.execute(
        select(
            PlannedWorkout.objective_id,
            func.min(PlannedWorkout.scheduled_date),
            func.max(PlannedWorkout.scheduled_date),
        )
        .where(
            PlannedWorkout.tenant_id == ident.tenant_id,
            PlannedWorkout.user_id == ident.user_id,
            PlannedWorkout.objective_id.is_not(None),
        )
        .group_by(PlannedWorkout.objective_id)
    ).all()
    block_start = {oid: lo_d for oid, lo_d, _hi in block_rows}
    for o in objectives:
        # Peak + (when set) the multi-day event window.
        for d in _days_clipped(o.target_date, o.event_end_date or o.target_date, start, end):
            entries.append(
                CalendarEntry(
                    kind="objective",
                    date=d,
                    id=o.id,
                    name=o.name,
                    status="peak" if d == o.target_date else "event",
                    objective_id=o.id,
                    objective_name=o.name,
                )
            )
        # Training-block band over the prep span (only when work is attributed).
        start_day = block_start.get(o.id)
        if start_day is not None and start_day < o.target_date:
            for d in _days_clipped(start_day, o.target_date, start, end):
                entries.append(
                    CalendarEntry(
                        kind="objective_block",
                        date=d,
                        id=o.id,
                        name=o.name,
                        status="block",
                        objective_id=o.id,
                        objective_name=o.name,
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


def _open_ailment_flags(db: Session, ident: Identity) -> list[AilmentFlag]:
    """The latest severity of every open ailment episode, for the same-day
    prescription gate (deterministic — see api.services.coach.ailment_gate).
    Episodes with no check-in yet (severity unknown) are excluded — the gate
    only reacts to a reported severity."""
    return [
        AilmentFlag(label=ep.label, severity=latest.severity)
        for ep in load_open_ailments(db, ident)
        if (latest := max(ep.check_ins, key=lambda c: (c.check_in_date, c.id), default=None))
        is not None
    ]


def _exercise_notes_with_gate(
    pe: PlannedExercise, flags: list[AilmentFlag]
) -> str | None:
    """``pe.notes`` with a lower-body/knee ailment warning prepended when the
    gate flags this exercise (see api.services.coach.ailment_gate)."""
    ex = pe.exercise
    muscles = frozenset((ex.primary_muscles or []) + (ex.secondary_muscles or []))
    warning = gate_exercise(ExerciseGateInput(exercise_id=pe.exercise_id, muscles=muscles), flags)
    if warning is None:
        return pe.notes
    return f"{warning}\n{pe.notes}" if pe.notes else warning


@router.post("/planned/{planned_id}/start", response_model=WorkoutSessionOut, status_code=201)
def start_planned(
    planned_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Seed a live session from the planned prescription; link + mark completed.

    Same-day ailment gate (deterministic, no LLM — vires-ops#50): a lower-
    body/knee episode at severity >=8 blocks the start outright (409); at
    severity >=5 the affected exercises get a ``notes`` warning but the
    session still starts. See api.services.coach.ailment_gate.
    """
    pw = _get_planned(db, planned_id, ident)

    # Idempotent: if already started, return the existing session.
    if pw.session_id is not None:
        existing = db.get(WorkoutSession, pw.session_id)
        if existing is not None:
            return _session_out(db, ident, existing)

    all_flags = relevant_ailment_flags(_open_ailment_flags(db, ident))
    blocking = blocking_flags(all_flags)
    if blocking:
        names = ", ".join(f"{f.label} ({f.severity}/10)" for f in blocking)
        raise HTTPException(
            409,
            f"Training is paused for this lower-body/knee ailment: {names}. "
            "Log an improved check-in or resolve the ailment before starting.",
        )

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
                notes=_exercise_notes_with_gate(pe, all_flags),
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


@router.post("/reschedule-missed", response_model=list[PlannedWorkoutOut])
def reschedule_missed_workouts(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[PlannedWorkoutOut]:
    """Mechanically slide missed workouts (planned, never started, date in
    the past) onto the next day that's actually fit to train on — no LLM
    call, no confirmation, always-on. "The coach" quietly keeps the calendar
    current; see ``api.services.reschedule`` for the recovery-aware landing
    logic (never adjacent to a hard athletic-calendar event, prefers spacing
    from other planned workouts). Distinct from the macro replan flow
    (``api.services.coach.replan``), which proposes restructuring a whole
    season and requires explicit user confirm.

    Idempotent: once a workout is moved to today-or-later it no longer
    matches the "missed" predicate, so calling this repeatedly (React
    StrictMode double-invoke, remounting the Plan tab) is a cheap no-op
    after the first real move — the frontend calls it unconditionally on
    every Plan-page mount.
    """
    moved = reschedule_missed(db, ident, date.today())
    return [to_planned_workout_out(pw) for pw in moved]


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
                coach_summary=program_coach_summary(p),
                objective_id=p.objective_id,
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


# --------------------------------------------------------------------------- #
# ICS calendar feed (subscribe from Google / Apple Calendar — read-only overlay)
# --------------------------------------------------------------------------- #
@router.get("/feed-url", response_model=FeedUrl)
def feed_url(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> FeedUrl:
    """The user's subscribe URL, minting the unguessable feed token on first use."""
    us = get_or_create_settings(db, ident)
    if not us.feed_token:
        us.feed_token = secrets.token_urlsafe(24)
        db.commit()
    return FeedUrl(token=us.feed_token, ics_path=f"/api/plan/feed/{us.feed_token}.ics")


@router.post("/feed-url/rotate", response_model=FeedUrl)
def rotate_feed_url(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> FeedUrl:
    """Rotate the token (invalidates any previously-shared feed URL)."""
    us = get_or_create_settings(db, ident)
    us.feed_token = secrets.token_urlsafe(24)
    db.commit()
    return FeedUrl(token=us.feed_token, ics_path=f"/api/plan/feed/{us.feed_token}.ics")


def _describe_planned(pw: PlannedWorkout, unit: str) -> str:
    lines: list[str] = []
    for pe in pw.exercises:
        name = pe.exercise.name
        if pe.target_duration_seconds:
            lines.append(f"{name}: {pe.target_sets or '?'}×{pe.target_duration_seconds}s")
        else:
            weight = f" @ {pe.target_weight}{unit}" if pe.target_weight is not None else ""
            lines.append(f"{name}: {pe.target_sets or '?'}×{pe.target_reps or '?'}{weight}")
    return "\n".join(lines) or (pw.notes or "")


def _describe_objective(o: Objective) -> str:
    bits = ["Target / peak day"]
    if o.sport:
        bits.append(f"sport: {o.sport}")
    return " · ".join(bits)


def _describe_session(ws: WorkoutSession) -> str:
    parts: list[str] = []
    for se in ws.exercises:
        working = [s for s in se.sets if not s.is_warmup and s.reps]
        if working:
            top = max(working, key=lambda s: (s.weight or 0))
            suffix = f", top {top.weight}×{top.reps}" if top.weight else ""
            parts.append(f"{se.exercise.name}: {len(working)} sets{suffix}")
        else:
            parts.append(se.exercise.name)
    return "\n".join(parts)


@router.get("/feed/{token}.ics")
def calendar_feed(
    token: str,
    db: Session = Depends(get_db),
) -> Response:
    """Public, UNAUTHENTICATED iCalendar feed (the token is the credential).

    Calendar apps fetch this anonymously and overlay the events; read-only. Google
    re-polls every ~8-24h, so updates are not instant — that's a subscription limit.
    """
    us = db.scalar(select(UserSettings).where(UserSettings.feed_token == token))
    if us is None:
        raise HTTPException(404, "Feed not found")
    now = datetime.now(UTC)

    events: list[IcsEvent] = []

    # User's dated objectives — drive the per-workout labels + the season bands.
    objectives = db.scalars(
        select(Objective)
        .where(
            Objective.tenant_id == us.tenant_id,
            Objective.user_id == us.user_id,
            Objective.kind == "dated",
            Objective.target_date.is_not(None),
        )
        .order_by(Objective.target_date)
    ).all()
    obj_by_id = {o.id: o for o in objectives}

    planned = db.scalars(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.tenant_id == us.tenant_id,
            PlannedWorkout.user_id == us.user_id,
        )
        .order_by(PlannedWorkout.scheduled_date)
    ).all()
    block_span: dict[int, tuple[date, date]] = {}  # objective_id -> (first, last) day
    for pw in planned:
        done = pw.status == "completed"
        desc = _describe_planned(pw, us.weight_unit)
        obj = obj_by_id.get(pw.objective_id)
        if obj is not None:
            desc = f"For: {obj.name}\n{desc}" if desc else f"For: {obj.name}"
            lo, hi = block_span.get(obj.id, (pw.scheduled_date, pw.scheduled_date))
            block_span[obj.id] = (min(lo, pw.scheduled_date), max(hi, pw.scheduled_date))
        events.append(
            IcsEvent(
                uid=f"planned-{pw.id}@vires.nousergon.ai",
                start=pw.scheduled_date,
                summary=("✓ " if done else "") + (pw.name or "Workout"),
                description=desc,
                dtstamp=pw.created_at or now,
            )
        )

    # Ad-hoc finished sessions (planned ones already appear above via their plan).
    sessions = db.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.tenant_id == us.tenant_id,
            WorkoutSession.user_id == us.user_id,
            WorkoutSession.planned_workout_id.is_(None),
            WorkoutSession.ended_at.is_not(None),
        )
        .order_by(WorkoutSession.started_at)
    ).all()
    for ws in sessions:
        events.append(
            IcsEvent(
                uid=f"session-{ws.id}@vires.nousergon.ai",
                start=ws.started_at.date(),
                summary="✓ " + (ws.name or "Workout"),
                description=_describe_session(ws),
                dtstamp=ws.ended_at or ws.started_at,
            )
        )

    # Season bands per dated objective: the training BLOCK (prep span, when there
    # are workouts attributed to it) and the EVENT/peak itself (a multi-day band
    # when it has an event window, else a single-day marker).
    for o in objectives:
        stamp = o.updated_at or o.created_at or now
        span = block_span.get(o.id)
        if span is not None:
            sport = f" — {o.sport}" if o.sport else ""
            events.append(
                IcsEvent(
                    uid=f"objective-block-{o.id}@vires.nousergon.ai",
                    start=span[0],
                    end=o.target_date,
                    summary=f"🏋 {o.name}{sport} block",
                    description=f"Training block building toward {o.name}.",
                    dtstamp=stamp,
                )
            )
        events.append(
            IcsEvent(
                uid=f"objective-{o.id}@vires.nousergon.ai",
                start=o.target_date,
                end=o.event_end_date,  # None => single-day peak (as before)
                summary=f"🎯 {o.name}",
                description=_describe_objective(o),
                dtstamp=stamp,
            )
        )

    ics = build_calendar("Vires Workouts", events)
    return Response(content=ics, media_type="text/calendar; charset=utf-8")
