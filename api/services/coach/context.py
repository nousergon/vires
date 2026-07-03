"""Build the coach's grounding/materialization context from the database.

Kept here (not in the pure ``materialize`` module) so the materializer stays
DB-free and unit-testable. This is the one place that reads the user's routines
and recent performance into the dataclasses the coach + materializer consume.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity, get_or_create_settings
from api.db.models import (
    ActivityDetail,
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
    ActivitySessionCtx,
    CoachObjectiveContext,
    ConstraintCtx,
    EventOccurrenceCtx,
    ExerciseCandidate,
    ObjectiveCtx,
)
from api.services.objective_focus import (
    dated_timeline,
    load_objectives,
    milestones_for,
    pick_focus,
)
from api.services.recurrence import expand_occurrences
from api.services.search import get_search_service

# Cap the candidate pool so the grounding context stays compact.
_MAX_CANDIDATES = 60
_HITS_PER_TERM = 4

# The coach's event lookahead. Default one mesocycle out, but extend to cover the
# full dated-objective season when it runs longer (so events near a far peak still
# register), capped so a weekly event against a distant objective can't blow up
# the grounding context.
_EVENT_WINDOW_WEEKS = 16
_EVENT_WINDOW_MAX_WEEKS = 52
# Keep the expanded occurrence list compact regardless of how many events /
# how far the window reaches — the coach needs the near pattern, not every future
# instance of a standing weekly commitment.
_MAX_OCCURRENCES_PER_EVENT = 26
_MAX_EVENT_OCCURRENCES = 40

# How far back logged generic activities stay relevant to fatigue/recovery
# reasoning — recent enough that a region's load is still "live," capped so a
# prolific cross-trainer can't blow up the grounding context.
_RECENT_ACTIVITY_WINDOW_DAYS = 7
_MAX_RECENT_ACTIVITIES = 20


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
    """The derived focus objective + active constraints generation runs against.

    Empty (no objective, no constraints) for users who haven't set one — the
    coach then behaves exactly as before (generic routine-driven generation).
    ``timeline`` carries every dated peak chronologically so the coach can
    periodize toward the next one while base-building for the rest."""
    objectives = load_objectives(db, ident)
    focus = pick_focus(objectives, date.today())
    obj_ctx = _to_objective_ctx(focus)
    # Attach the focus objective's training milestones (its sub-objectives) so the
    # coach periodizes a mini-taper/retest around each benchmark inside the block.
    if obj_ctx is not None and focus is not None:
        obj_ctx.milestones = [
            c
            for m in milestones_for(objectives, focus.id)
            if (c := _to_objective_ctx(m)) is not None
        ]
    timeline = [_to_objective_ctx(o) for o in dated_timeline(objectives)]
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
    events = _build_event_ctxs(db, ident, timeline, date.today())
    recent_activities = _build_recent_activities(db, ident, date.today())
    return CoachObjectiveContext(
        objective=obj_ctx,
        constraints=con_ctxs,
        candidates=candidates,
        timeline=timeline,
        events=events,
        recent_activities=recent_activities,
    )


def _event_window(
    timeline: list[ObjectiveCtx], today: date
) -> tuple[date, date]:
    """The [start, end] date range over which upcoming events are expanded.

    Starts today; runs a default mesocycle out, extended to reach the furthest
    dated peak in the season (so events near a far objective still register),
    hard-capped at ``_EVENT_WINDOW_MAX_WEEKS`` so a weekly event can't fan out
    unbounded."""
    window_end = today + timedelta(weeks=_EVENT_WINDOW_WEEKS)
    peak_ends = [
        (o.event_end_date or o.target_date)
        for o in timeline
        if o is not None and (o.event_end_date or o.target_date) is not None
    ]
    if peak_ends:
        window_end = max(window_end, max(peak_ends))
    hard_cap = today + timedelta(weeks=_EVENT_WINDOW_MAX_WEEKS)
    return today, min(window_end, hard_cap)


def _build_event_ctxs(
    db: Session, ident: Identity, timeline: list[ObjectiveCtx], today: date
) -> list[EventOccurrenceCtx]:
    """Athletic events (recurrence-expanded within the planning window) the coach
    must train *around* — the load-accounting axis (#33). Empty for users with no
    events (the coach then behaves exactly as before).

    Formerly a dedicated ``CalendarEvent`` query; now any ``ActivityDetail``
    row not yet closed out (``ended_at IS NULL``) — a `CalendarEvent` row was
    implicitly "a constraint forever" (it had no ``ended_at`` concept), and
    that's the merged equivalent. An already-logged activity (``ended_at``
    set) is history, not a forward constraint, and is excluded here — it
    shows up instead in ``_build_recent_activities``.
    """
    rows = db.execute(
        select(WorkoutSession, ActivityDetail)
        .join(ActivityDetail, ActivityDetail.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.session_type == "activity",
            WorkoutSession.ended_at.is_(None),
        )
        .order_by(WorkoutSession.started_at)
    ).all()
    if not rows:
        return []
    window_start, window_end = _event_window(timeline, today)
    out: list[EventOccurrenceCtx] = []
    for ws, ad in rows:
        occurrences = expand_occurrences(
            ws.started_at.date(), ad.event_end_date, ad.recurrence, window_start, window_end
        )
        for occ_date, occ_end in occurrences[:_MAX_OCCURRENCES_PER_EVENT]:
            out.append(
                EventOccurrenceCtx(
                    name=ws.name or "Activity",
                    template_key=ad.template_key,
                    occurrence_date=occ_date,
                    occurrence_end_date=occ_end,
                    sport=ad.sport,
                    load={
                        "regions": ad.regions,
                        "intensity": ad.intensity,
                        "duration_min": ad.duration_s // 60 if ad.duration_s else None,
                    },
                    recurrence=ad.recurrence,
                    objective_id=ad.objective_id,
                    notes=ws.notes,
                )
            )
    # Soonest first, and keep the list compact regardless of event count.
    out.sort(key=lambda e: e.occurrence_date)
    return out[:_MAX_EVENT_OCCURRENCES]


def _build_recent_activities(
    db: Session, ident: Identity, today: date
) -> list[ActivitySessionCtx]:
    """Activity sessions (climbing, swimming, yoga, walk/run/hike, ...) logged
    within the trailing window — load already absorbed, factored into today's
    fatigue/recovery reasoning. Empty for users who haven't logged one (the
    coach then behaves exactly as before)."""
    # WorkoutSession.started_at is a UTCDateTime column — compare against a
    # tz-aware datetime, not a bare date (UTCDateTime.process_bind_param
    # requires .tzinfo).
    window_start = datetime.combine(
        today - timedelta(days=_RECENT_ACTIVITY_WINDOW_DAYS), time.min, tzinfo=UTC
    )
    rows = db.execute(
        select(WorkoutSession, ActivityDetail)
        .join(ActivityDetail, ActivityDetail.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.tenant_id == ident.tenant_id,
            WorkoutSession.user_id == ident.user_id,
            WorkoutSession.session_type == "activity",
            WorkoutSession.started_at >= window_start,
            # Closed-out (actuals recorded) only — since the CalendarEvent
            # merge, a future/planned/not-yet-happened activity can also
            # have started_at in this trailing window (e.g. logged
            # "tomorrow"); that's an upcoming constraint (_build_event_ctxs),
            # not load already absorbed.
            WorkoutSession.ended_at.is_not(None),
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(_MAX_RECENT_ACTIVITIES)
    ).all()
    return [
        ActivitySessionCtx(
            name=ws.name or "Activity",
            session_date=ws.started_at.date(),
            regions=ad.regions,
            intensity=ad.intensity,
            duration_min=ad.duration_s // 60 if ad.duration_s else None,
            pack_weight_kg=ad.pack_weight_kg,
            metabolic_cost_kj=ad.metabolic_cost_kj,
        )
        for ws, ad in rows
    ]


def _to_objective_ctx(o: Objective | None) -> ObjectiveCtx | None:
    """Project an ``Objective`` row into the DB-free coach context dataclass."""
    if o is None:
        return None
    return ObjectiveCtx(
        id=o.id,
        name=o.name,
        kind=o.kind,
        target_date=o.target_date,
        event_end_date=o.event_end_date,
        sport=o.sport,
        demands_profile=o.demands_profile,
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
