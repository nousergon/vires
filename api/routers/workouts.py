"""Workout sessions: start (empty or from a template), log sets, finish, history."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.identity import Identity, current_identity, get_or_create_settings
from api.db.models import (
    ActivityDetail,
    Objective,
    PlannedWorkout,
    SessionExercise,
    SetEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from api.db.session import get_db
from api.schemas.exercise import ExercisePerformance, PerformedSet
from api.schemas.workout import (
    ActivityDetailOut,
    ActivityLogIn,
    ActivityTemplateOut,
    MaterializeOccurrenceIn,
    SessionExerciseIn,
    SessionExerciseOut,
    SessionExerciseReorder,
    SessionExerciseReplace,
    SessionExerciseUpdate,
    SetIn,
    SetOut,
    SetUpdate,
    WorkoutFinish,
    WorkoutSessionOut,
    WorkoutSessionUpdate,
    WorkoutStart,
    WorkoutSummary,
)
from api.serializers import dumbbell_seed_weight, to_exercise_brief
from api.services.activity_templates import ACTIVITY_TEMPLATES
from api.services.ailments import exercise_notes_with_gate, open_ailment_flags
from api.services.coach.ailment_gate import blocking_flags, relevant_ailment_flags
from api.services.coach.autoregulate import autoregulate_after_session
from api.services.load.pandolf import ruck_metabolic_cost_kj

log = logging.getLogger("vires.autoregulate")

router = APIRouter(prefix="/workouts", tags=["workouts"])


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware_utc(dt: datetime) -> datetime:
    """A client-supplied ``started_at`` may arrive naive (no offset) — treat
    it as UTC, matching how ``UTCDateTime`` stores/reads every timestamp in
    this app, so it can be safely compared against ``_now()``."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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
        client_uuid=s.client_uuid,
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
                        duration_seconds=s.duration_seconds,
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


def _activity_out(ad: ActivityDetail | None) -> ActivityDetailOut | None:
    if ad is None:
        return None
    return ActivityDetailOut(
        template_key=ad.template_key,
        duration_s=ad.duration_s,
        regions=ad.regions,
        intensity=ad.intensity,
        pack_weight_kg=ad.pack_weight_kg,
        bodyweight_kg=ad.bodyweight_kg,
        distance_m=ad.distance_m,
        elevation_gain_m=ad.elevation_gain_m,
        terrain=ad.terrain,
        metabolic_cost_kj=ad.metabolic_cost_kj,
        source=ad.source,
        sport=ad.sport,
        event_end_date=ad.event_end_date,
        recurrence=ad.recurrence,
        objective_id=ad.objective_id,
    )


def _session_out(db: Session, ident: Identity, ws: WorkoutSession) -> WorkoutSessionOut:
    return WorkoutSessionOut(
        id=ws.id,
        session_type=ws.session_type,
        name=ws.name,
        started_at=ws.started_at,
        ended_at=ws.ended_at,
        notes=ws.notes,
        tags=ws.tags or [],
        energy_level=ws.energy_level,
        workout_intensity=ws.workout_intensity,
        challenge_level=ws.challenge_level,
        template_id=ws.template_id,
        exercises=[_se_out(db, ident, se) for se in ws.exercises],
        activity=_activity_out(ws.activity_detail),
        recurrence_source_id=ws.recurrence_source_id,
    )


def _require_owned_objective(db: Session, ident: Identity, objective_id: int) -> None:
    o = db.get(Objective, objective_id)
    if o is None or o.tenant_id != ident.tenant_id or o.user_id != ident.user_id:
        raise HTTPException(404, "Objective not found")


# --------------------------------------------------------------------------- #
# unit conversion — display units in → canonical SI. Distance/elevation unit is
# keyed off the account's weight_unit ('lb' ⇒ imperial mi/ft, 'kg' ⇒ metric km/m)
# so a route-capable activity needs no separate distance-unit setting in Tier 0.
# --------------------------------------------------------------------------- #
_LB_TO_KG = 0.45359237
_MILE_TO_M = 1609.344
_KM_TO_M = 1000.0
_FOOT_TO_M = 0.3048


def _weight_to_kg(v: float, weight_unit: str) -> float:
    return v if weight_unit == "kg" else v * _LB_TO_KG


def _distance_to_m(v: float | None, weight_unit: str) -> float | None:
    if v is None:
        return None
    return v * (_KM_TO_M if weight_unit == "kg" else _MILE_TO_M)


def _elevation_to_m(v: float | None, weight_unit: str) -> float | None:
    if v is None:
        return None
    return v * (1.0 if weight_unit == "kg" else _FOOT_TO_M)


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
    """Start an ad-hoc session — empty, or seeded from a template.

    Same-day ailment gate (deterministic, no LLM — vires-ops#58, extending
    the planned-start gate in api.routers.plan to this path too): a lower-
    body/knee episode at severity >=8 blocks the start outright (409); at
    severity >=5 the affected template exercises get a ``notes`` warning but
    the session still starts. See api.services.coach.ailment_gate.
    """
    all_flags = relevant_ailment_flags(open_ailment_flags(db, ident))
    blocking = blocking_flags(all_flags)
    if blocking:
        names = ", ".join(f"{f.label} ({f.severity}/10)" for f in blocking)
        raise HTTPException(
            409,
            f"Training is paused for this lower-body/knee ailment: {names}. "
            "Log an improved check-in or resolve the ailment before starting.",
        )

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
                target_weight=dumbbell_seed_weight(te.target_weight, te.exercise.equipment),
                target_duration_seconds=te.target_duration_seconds,
                rest_seconds=te.rest_seconds,
                notes=exercise_notes_with_gate(te.exercise_id, te.exercise, te.notes, all_flags),
            )
            for te in tpl.exercises
        ]
    ws = WorkoutSession(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        name=name,
        started_at=_now(),
        tags=body.tags or [],
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


@router.get("/activity-templates", response_model=list[ActivityTemplateOut])
def list_activity_templates() -> list[ActivityTemplateOut]:
    """The fixed activity-template catalog the quick-log form offers as one-tap
    starting points (see api.services.activity_templates)."""
    return ACTIVITY_TEMPLATES


@router.post("/activity", response_model=WorkoutSessionOut, status_code=201)
def log_activity(
    body: ActivityLogIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Log an activity — a completed cross-training/locomotion session, OR a
    future/recurring/multi-day/objective-anchored one (what used to require
    a separate ``CalendarEvent``). Optionally with a route and/or a weighted
    pack.

    Tier 0: a coarse regions/intensity estimate (template-prefilled, always
    user-editable) rather than a bespoke schema per activity — see
    ``ActivityDetail`` for why. No set-by-set flow and no double-progression
    autoregulation.

    There is no "planned" flag: whether the row is upcoming or already
    happened is derived purely from ``started_at``/``ended_at`` vs. "now" at
    read time. A recurring ('weekly') row is a perpetual series template and
    is never itself closed out; otherwise ``ended_at`` is set iff the log is
    backdated to today-or-earlier (the existing quick-log behavior), and left
    null for a future date — the user fills in what happened later via
    ``PATCH /workouts/{id}``.

    Pack-weight-adjusted metabolic cost (Pandolf) is computed only when BOTH
    pack weight and bodyweight are present — never with a synthetic 0kg pack,
    so an unloaded walk/run/hike simply has no load number rather than a
    fabricated one.
    """
    us = get_or_create_settings(db, ident)
    unit = us.weight_unit

    distance_m = _distance_to_m(body.distance, unit)
    elevation_m = _elevation_to_m(body.elevation_gain, unit)
    pack_kg = _weight_to_kg(body.pack_weight, unit) if body.pack_weight is not None else None
    body_kg = _weight_to_kg(body.bodyweight, unit) if body.bodyweight is not None else None

    cost_kj = None
    if pack_kg is not None and body_kg is not None:
        cost_kj = ruck_metabolic_cost_kj(
            bodyweight_kg=body_kg,
            pack_weight_kg=pack_kg,
            distance_m=distance_m,
            elevation_gain_m=elevation_m,
            duration_s=body.duration_s,
            terrain=body.terrain,
        )

    started = body.started_at or _now()
    if body.event_end_date is not None and body.event_end_date < started.date():
        raise HTTPException(400, "event_end_date must be on or after the start date")
    if body.objective_id is not None:
        _require_owned_objective(db, ident, body.objective_id)

    is_past_or_now = _as_aware_utc(started) <= _now()
    ended_at = None if body.recurrence == "weekly" else (started if is_past_or_now else None)

    ws = WorkoutSession(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        session_type="activity",
        name=body.name,
        started_at=started,
        ended_at=ended_at,
        activity_detail=ActivityDetail(
            template_key=body.template_key,
            duration_s=body.duration_s,
            regions=body.regions,
            intensity=body.intensity,
            pack_weight_kg=pack_kg,
            bodyweight_kg=body_kg,
            distance_m=distance_m,
            elevation_gain_m=elevation_m,
            terrain=body.terrain,
            metabolic_cost_kj=cost_kj,
            source=body.source,
            sport=body.sport,
            event_end_date=body.event_end_date,
            recurrence=body.recurrence,
            objective_id=body.objective_id,
        ),
    )
    db.add(ws)
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
            # Retrospective history only — a future/planned activity (no
            # prior equivalent existed for strength, which is always created
            # at "now") doesn't belong in the log until it's happened.
            WorkoutSession.started_at <= _now(),
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
                session_type=ws.session_type,
                name=ws.name,
                started_at=ws.started_at,
                ended_at=ws.ended_at,
                exercise_count=len(ws.exercises),
                set_count=set_count,
                total_volume=round(volume, 2),
                tags=ws.tags or [],
                energy_level=ws.energy_level,
                workout_intensity=ws.workout_intensity,
                challenge_level=ws.challenge_level,
                activity=_activity_out(ws.activity_detail),
            )
        )
    return out


@router.get("/tags", response_model=list[str])
def list_workout_tags(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[str]:
    """Every tag the user has ever applied to a session, most-used first —
    powers the tag quick-complete chips in ``TagsEditor``. Declared ahead of
    ``/{session_id}`` so it isn't shadowed by that path param."""
    rows = db.scalars(
        select(WorkoutSession.tags).where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
        )
    ).all()
    counts: dict[str, int] = {}
    for tags in rows:
        for tag in tags or []:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], t.lower()))


@router.get("/{session_id}", response_model=WorkoutSessionOut)
def get_workout(
    session_id: int,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    return _session_out(db, ident, _get_session(db, session_id, ident))


_ACTIVITY_ONLY_FIELDS = frozenset(
    {
        "template_key", "duration_s", "regions", "intensity", "distance",
        "elevation_gain", "terrain", "source", "pack_weight", "bodyweight",
        "sport", "recurrence", "event_end_date", "objective_id",
    }
)


@router.patch("/{session_id}", response_model=WorkoutSessionOut)
def update_workout(
    session_id: int,
    body: WorkoutSessionUpdate,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Edit a session in place. Serves both "edit a still-open future/planned
    activity" and "log what actually happened on one" — including
    ``ended_at`` in the payload is what closes it out; there's no separate
    status transition (see ``WorkoutSessionUpdate``)."""
    ws = _get_session(db, session_id, ident)
    data = body.model_dump(exclude_unset=True)

    if (_ACTIVITY_ONLY_FIELDS & data.keys()) and ws.session_type != "activity":
        raise HTTPException(400, "These fields only apply to an activity session")

    if "name" in data and data["name"] is not None:
        ws.name = data["name"]
    if "started_at" in data and data["started_at"] is not None:
        ws.started_at = data["started_at"]
    if "ended_at" in data and data["ended_at"] is not None:
        ws.ended_at = data["ended_at"]
    if "notes" in data:
        ws.notes = data["notes"]
    # Session-tracking fields — valid on any session type.
    if "tags" in data and data["tags"] is not None:
        ws.tags = data["tags"]
    if "energy_level" in data:
        ws.energy_level = data["energy_level"]
    if "workout_intensity" in data:
        ws.workout_intensity = data["workout_intensity"]
    if "challenge_level" in data:
        ws.challenge_level = data["challenge_level"]

    ad = ws.activity_detail
    if ad is not None:
        if (
            "recurrence" in data
            and data["recurrence"] == "weekly"
            and ws.recurrence_source_id is not None
        ):
            raise HTTPException(400, "A materialized occurrence can't itself recur")
        if "objective_id" in data and data["objective_id"] is not None:
            _require_owned_objective(db, ident, data["objective_id"])

        if "template_key" in data:
            ad.template_key = data["template_key"]
        if "duration_s" in data:
            ad.duration_s = data["duration_s"]
        if "regions" in data and data["regions"] is not None:
            ad.regions = data["regions"]
        if "intensity" in data and data["intensity"] is not None:
            ad.intensity = data["intensity"]
        if "sport" in data:
            ad.sport = data["sport"]
        if "recurrence" in data and data["recurrence"] is not None:
            ad.recurrence = data["recurrence"]
        if "event_end_date" in data:
            ad.event_end_date = data["event_end_date"]
        if "objective_id" in data:
            ad.objective_id = data["objective_id"]

        us = get_or_create_settings(db, ident)
        unit = us.weight_unit
        if "distance" in data:
            ad.distance_m = _distance_to_m(data["distance"], unit)
        if "elevation_gain" in data:
            ad.elevation_gain_m = _elevation_to_m(data["elevation_gain"], unit)
        if "terrain" in data and data["terrain"] is not None:
            ad.terrain = data["terrain"]
        if "source" in data and data["source"] is not None:
            ad.source = data["source"]
        if "pack_weight" in data:
            pack = data["pack_weight"]
            ad.pack_weight_kg = _weight_to_kg(pack, unit) if pack is not None else None
        if "bodyweight" in data:
            bw = data["bodyweight"]
            ad.bodyweight_kg = _weight_to_kg(bw, unit) if bw is not None else None
        if ad.pack_weight_kg is not None and ad.bodyweight_kg is not None:
            ad.metabolic_cost_kj = ruck_metabolic_cost_kj(
                bodyweight_kg=ad.bodyweight_kg,
                pack_weight_kg=ad.pack_weight_kg,
                distance_m=ad.distance_m,
                elevation_gain_m=ad.elevation_gain_m,
                duration_s=ad.duration_s,
                terrain=ad.terrain,
            )

        if ad.event_end_date is not None and ad.event_end_date < ws.started_at.date():
            raise HTTPException(400, "event_end_date must be on or after the start date")

    db.commit()
    db.refresh(ws)
    return _session_out(db, ident, ws)


@router.post("/{session_id}/occurrences", response_model=WorkoutSessionOut, status_code=201)
def materialize_occurrence(
    session_id: int,
    body: MaterializeOccurrenceIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Turn one virtual (expanded-on-read, never-persisted) occurrence of a
    recurring activity into a real, linked row — fired when the user taps a
    future occurrence of a weekly series (e.g. "next Tuesday's league game")
    to log what happened or just to view/edit that specific date."""
    template = _get_session(db, session_id, ident)
    if template.session_type != "activity" or template.activity_detail is None:
        raise HTTPException(400, "Not an activity session")
    ad = template.activity_detail
    if ad.recurrence != "weekly":
        raise HTTPException(400, "Session is not a recurring series")

    # Idempotent: re-tapping an already-materialized occurrence returns the
    # existing row rather than creating a duplicate (no DB-level uniqueness
    # constraint — matches this codebase's existing idempotent-by-predicate
    # style, e.g. api.services.reschedule).
    day_start = datetime.combine(body.occurrence_date, datetime.min.time())
    existing = db.scalars(
        select(WorkoutSession).where(
            WorkoutSession.recurrence_source_id == session_id,
            WorkoutSession.started_at >= day_start,
            WorkoutSession.started_at < day_start + timedelta(days=1),
        )
    ).first()
    if existing is not None:
        return _session_out(db, ident, existing)

    occurrence_dt = datetime.combine(body.occurrence_date, template.started_at.time())
    occurrence = WorkoutSession(
        tenant_id=ident.tenant_id,
        user_id=ident.user_id,
        session_type="activity",
        name=template.name,
        started_at=occurrence_dt,
        ended_at=None,
        notes=template.notes,
        recurrence_source_id=template.id,
        activity_detail=ActivityDetail(
            template_key=ad.template_key,
            regions=ad.regions,
            intensity=ad.intensity,
            duration_s=ad.duration_s,
            sport=ad.sport,
            # A materialized occurrence is a single concrete instance, never
            # itself a recurring template or a multi-day span.
            recurrence="none",
            event_end_date=None,
            objective_id=ad.objective_id,
        ),
    )
    db.add(occurrence)
    db.commit()
    db.refresh(occurrence)
    return _session_out(db, ident, occurrence)


@router.post("/{session_id}/finish", response_model=WorkoutSessionOut)
def finish_workout(
    session_id: int,
    body: WorkoutFinish | None = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> WorkoutSessionOut:
    """Close out a session, optionally recording the end-of-workout 1–10
    energy/intensity/challenge self-report. The ratings are applied whenever
    supplied (even on a re-finish of an already-closed session, so a skipped
    prompt can be filled in later), but ``ended_at`` is only stamped once."""
    ws = _get_session(db, session_id, ident)
    if body is not None:
        if body.energy_level is not None:
            ws.energy_level = body.energy_level
        if body.workout_intensity is not None:
            ws.workout_intensity = body.workout_intensity
        if body.challenge_level is not None:
            ws.challenge_level = body.challenge_level
    if ws.ended_at is None:
        ws.ended_at = _now()
        db.commit()  # the workout log is the primary deliverable — land it first
        db.refresh(ws)
        # Then adapt the upcoming plan. Best-effort + AFTER the finish commit:
        # autoregulation is secondary to recording the workout, so it must never
        # fail a completed session (see _maybe_autoregulate).
        _maybe_autoregulate(db, ident, ws)
    else:
        # Already closed — just persist any ratings supplied on this call.
        db.commit()
        db.refresh(ws)
    return _session_out(db, ident, ws)


def _maybe_autoregulate(
    db: Session, ident: Identity, ws: WorkoutSession
) -> None:
    """Run deterministic autoregulation off a finished session, best-effort.

    Swallows + WARN-logs any failure: the finish already committed, so a bad
    adjustment must not surface as a 500 on a workout the user actually did. The
    WARN log is the failure-recording surface (durable audit = vires-ops#18)."""
    if not get_settings().autoregulation_enabled:
        return
    try:
        applied = autoregulate_after_session(db, ident, ws)
        if applied:
            db.commit()
            for a in applied:
                log.info(
                    "autoregulation session=%s exercise=%s verdict=%s "
                    "weight_delta=%s duration_delta=%s occurrences=%s",
                    ws.id, a.exercise_id, a.verdict, a.weight_delta,
                    a.duration_delta_seconds, a.occurrences_adjusted,
                )
        else:
            db.rollback()  # no-op: discard any read-state, leave nothing pending
    except Exception:  # noqa: BLE001 — secondary best-effort path; see docstring
        db.rollback()
        log.warning("autoregulation failed for session %s", ws.id, exc_info=True)


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
    # Pre-create planned set rows the same way a from-template exercise gets
    # them (Strong-style: ready-to-fill rows, not a blank list) — a no-op
    # unless the caller supplied target_sets (see WorkoutPage's addExercise,
    # which seeds it from the user's default_sets/default_reps setting).
    _seed_planned_sets(db, ident, se)
    db.commit()
    db.refresh(se)
    return _se_out(db, ident, se)


@router.patch("/{session_id}/exercises/reorder", response_model=list[SessionExerciseOut])
def reorder_session_exercises(
    session_id: int,
    body: SessionExerciseReorder,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> list[SessionExerciseOut]:
    """Drag-and-drop reorder: reassign ``order_index`` 0..n-1 from
    ``exercise_ids``' order, in one transaction. Declared ahead of
    ``/{se_id}`` so "reorder" isn't parsed as an exercise id."""
    ws = _get_session(db, session_id, ident)
    by_id = {se.id: se for se in ws.exercises}
    if set(body.exercise_ids) != set(by_id):
        raise HTTPException(400, "exercise_ids must match the session's current exercises exactly")
    for index, se_id in enumerate(body.exercise_ids):
        by_id[se_id].order_index = index
    db.commit()
    # `ws.exercises` is order_by="order_index", but a loaded collection isn't
    # re-sorted just because a child's ordering column changed in place —
    # expire it so the next access re-queries in the new order.
    db.expire(ws, ["exercises"])
    return [_se_out(db, ident, se) for se in ws.exercises]


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


@router.post("/{session_id}/exercises/{se_id}/replace", response_model=SessionExerciseOut)
def replace_session_exercise(
    session_id: int,
    se_id: int,
    body: SessionExerciseReplace,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> SessionExerciseOut:
    """Swap this slot's exercise for another, in place — the one-tap "replace"
    that spares the user a manual remove + re-add + drag-back-into-sequence.

    Keeps the slot (same ``order_index`` and id) and its set/rep/rest scheme,
    but retargets it and re-seeds fresh set rows for the new move: the old
    exercise-specific weight/hold-duration and any set rows are discarded (a
    replaced move wasn't the one you did). Replacing an exercise with itself
    is a no-op — the existing rows are left untouched."""
    from api.db.models import Exercise

    ws = _get_session(db, session_id, ident)
    se = _get_se(db, ws, se_id)
    if body.exercise_id == se.exercise_id:
        return _se_out(db, ident, se)
    ex = db.get(Exercise, body.exercise_id)
    if ex is None or (ex.tenant_id is not None and ex.tenant_id != ident.tenant_id):
        raise HTTPException(400, f"Unknown exercise_id {body.exercise_id}")

    se.exercise_id = body.exercise_id
    # Exercise-specific targets and the prior move's logged/planned sets don't
    # carry across a swap; the set/rep count and rest cadence do (same slot in
    # the routine). notes was written for the old exercise, so clear it too.
    se.target_weight = None
    se.target_duration_seconds = None
    se.notes = None
    for s in list(se.sets):
        db.delete(s)
    db.flush()
    db.refresh(se)
    # Re-seed ready-to-fill rows for the new move (from ITS own history, else
    # the retained target_reps), exactly like a fresh from-template exercise.
    _seed_planned_sets(db, ident, se)
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
    # Offline-first idempotency (vires-ops#48): the PWA mints a client_uuid per
    # logged set and replays queued writes on reconnect. A replay of a set that
    # already landed must NOT append a duplicate — return the existing row.
    # Matches this codebase's idempotent-by-predicate style (see
    # materialize_occurrence). The (session_exercise_id, client_uuid) unique
    # index is the backstop against a concurrent-replay race.
    if body.client_uuid is not None:
        existing = next(
            (s for s in se.sets if s.client_uuid == body.client_uuid), None
        )
        if existing is not None:
            return _set_out(existing)
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
        client_uuid=body.client_uuid,
    )
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent replay of the same client_uuid — the
        # other request created the row. Roll back and return the winner, so
        # both replays see success (idempotent).
        db.rollback()
        if body.client_uuid is not None:
            winner = db.scalars(
                select(SetEntry).where(
                    SetEntry.session_exercise_id == se.id,
                    SetEntry.client_uuid == body.client_uuid,
                )
            ).first()
            if winner is not None:
                return _set_out(winner)
        raise
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
