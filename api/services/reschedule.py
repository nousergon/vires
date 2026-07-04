"""Automatic single-workout rescheduling — the light, deterministic "coach
quietly moves a missed day forward" pass (Brian: missed a Thursday workout
to a knee flare-up, picked it up Friday by hand, expected the app to have
already pushed the missed day forward on its own).

Deliberately NOT the macro replan flow (``api.services.coach.replan``): that
proposes restructuring a whole season, calls an LLM, and requires explicit
user confirm before anything is written, firing only once >=2 sessions are
missed. This is mechanical, free, instant, and always-on — it moves ONE
missed day at a time onto the next day that's actually fit to train on,
framed to the user as "the coach did this," never asked about.

"Fit to train on" is recovery-aware, not just "the first empty square on the
calendar": a missed workout must never land the day of, before, or after a
hard-intensity activity/event (a big hike, a race — what the coach trains
AROUND; formerly a separate ``CalendarEvent``, now just an ``ActivityDetail``
row with ``recurrence``/``event_end_date`` set, see
``api.services.recurrence``), and PREFERABLY doesn't land immediately
adjacent to another already-scheduled ``PlannedWorkout`` either (a soft
preference — used as a fallback rather than leaving the workout unscheduled).

``plan_reschedule_moves`` is pure (no DB) so it's unit-testable in
isolation; ``reschedule_missed`` is the thin DB-querying + mutating wrapper —
mirrors the ``evaluate_triggers``/``detect_triggers`` split in
``api.services.coach.replan``.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity
from api.db.models import ActivityDetail, PlannedWorkout, WorkoutSession
from api.services.recurrence import expand_occurrences

# Flat lookahead when a missed workout has no program (or its program has no
# end_date) to bound the search against.
DEFAULT_HORIZON_DAYS = 13


def plan_reschedule_moves(
    missed: list[PlannedWorkout],
    occupied: set[date],
    hard_blocked: set[date],
    today: date,
) -> list[tuple[PlannedWorkout, date]]:
    """Decide where each missed workout lands (pure).

    Oldest ``scheduled_date`` first (ties broken by id), so the
    longest-overdue workout gets first pick of the earliest fit day.
    ``occupied`` is mutated as slots are claimed — both so two missed
    workouts in the same pass never collide onto the same day, and so a
    workout placed earlier in the pass correctly becomes a soft-preference
    neighbor for the next one placed.

    ``hard_blocked`` = every day within reach of a hard-intensity activity
    (the activity's own span plus one day of buffer on each side) — never a
    valid landing day, no exceptions. A hard activity demands rest on BOTH
    sides (arrive fresh, then recover), so this check is symmetric.

    For each missed workout: walk ``today`` .. its horizon and collect every
    day that is neither in ``occupied`` nor in ``hard_blocked`` (the hard
    constraints). Among those, PREFER the earliest one whose *following* day
    isn't already `occupied` — landing the day immediately BEFORE an
    already-fixed planned workout removes that workout's rest day, which is
    worth avoiding when a better slot exists. This check is deliberately
    ASYMMETRIC (only looks forward, not at the day before the candidate):
    two ordinary lifting days back-to-back is a normal, acceptable split, so
    landing right after an occupied day is never penalized — only landing
    right before one is. It's a soft preference, not a hard filter: if every
    hard-valid day in the horizon fails it, fall back to the earliest
    hard-valid day anyway. A workout with no hard-valid day at all within
    its horizon is omitted from the result — left untouched, still shows as
    missed.
    """
    ordered = sorted(missed, key=lambda pw: (pw.scheduled_date, pw.id))
    moves: list[tuple[PlannedWorkout, date]] = []
    for pw in ordered:
        horizon_end = (
            pw.program.end_date
            if pw.program_id and pw.program is not None and pw.program.end_date is not None
            else today + timedelta(days=DEFAULT_HORIZON_DAYS)
        )

        candidates: list[date] = []
        d = today
        while d <= horizon_end:
            if d not in occupied and d not in hard_blocked:
                candidates.append(d)
            d += timedelta(days=1)

        def _removes_rest_before_next_workout(day: date) -> bool:
            return (day + timedelta(days=1)) in occupied

        landing = next((d for d in candidates if not _removes_rest_before_next_workout(d)), None)
        if landing is None and candidates:
            landing = candidates[0]  # soft fallback: earliest hard-valid day

        if landing is not None:
            occupied.add(landing)
            moves.append((pw, landing))
    return moves


def _hard_blocked_dates(
    activity_rows: list[tuple[WorkoutSession, ActivityDetail]],
    window_start: date,
    window_end: date,
) -> set[date]:
    """Expand hard-intensity activities (weekly recurrence included, via
    ``api.services.recurrence.expand_occurrences``) into the set of days a
    missed workout must not land on: the activity's own span, plus one day
    of buffer on each side of that span. 'moderate'/'light' activities
    impose no buffer."""
    blocked: set[date] = set()
    for ws, ad in activity_rows:
        if ad.intensity != "hard":
            continue
        for occ_start, occ_end in expand_occurrences(
            ws.started_at.date(), ad.event_end_date, ad.recurrence, window_start, window_end
        ):
            span_end = occ_end or occ_start
            d = occ_start - timedelta(days=1)
            last = span_end + timedelta(days=1)
            while d <= last:
                blocked.add(d)
                d += timedelta(days=1)
    return blocked


def reschedule_missed(
    db: Session, ident: Identity, today: date | None = None
) -> list[PlannedWorkout]:
    """DB-backed pass: find missed workouts, compute moves, persist them.

    Idempotent by construction: once moved to >= today a workout no longer
    matches the "missed" predicate (``scheduled_date < today``), so calling
    this repeatedly (React StrictMode double-invoke, remounting the Plan
    tab) is a cheap no-op after the first real move — safe to call
    unconditionally on every page load."""
    if today is None:
        today = date.today()

    missed = list(
        db.scalars(
            select(PlannedWorkout).where(
                PlannedWorkout.tenant_id == ident.tenant_id,
                PlannedWorkout.user_id == ident.user_id,
                PlannedWorkout.status == "planned",
                PlannedWorkout.session_id.is_(None),
                PlannedWorkout.scheduled_date < today,
            )
        ).all()
    )
    if not missed:
        return []

    horizon_end = max(
        (
            pw.program.end_date
            if pw.program_id and pw.program is not None and pw.program.end_date is not None
            else today + timedelta(days=DEFAULT_HORIZON_DAYS)
        )
        for pw in missed
    )

    occupied = set(
        db.scalars(
            select(PlannedWorkout.scheduled_date).where(
                PlannedWorkout.tenant_id == ident.tenant_id,
                PlannedWorkout.user_id == ident.user_id,
                PlannedWorkout.scheduled_date >= today,
            )
        ).all()
    )

    # Every activity within reach, regardless of open/closed — a `CalendarEvent`
    # row was ALWAYS a constraint (it had no `ended_at`/closed concept at
    # all), and the recovery need a hard-intensity day imposes on its
    # neighbors doesn't stop mattering just because it's since been logged.
    # Unlike `_build_event_ctxs` (coach planning — "what's still upcoming,"
    # correctly `ended_at IS NULL` there), this is a narrower mechanical
    # adjacency check, and it's already bounded to the near-term window below
    # (`expand_occurrences`' own span-intersection check excludes anything
    # outside it) — no separate open/closed gate needed.
    activity_rows = list(
        db.execute(
            select(WorkoutSession, ActivityDetail)
            .join(ActivityDetail, ActivityDetail.session_id == WorkoutSession.id)
            .where(
                WorkoutSession.tenant_id == ident.tenant_id,
                WorkoutSession.user_id == ident.user_id,
                WorkoutSession.session_type == "activity",
            )
        ).all()
    )
    # Padded by one day on each side so a hard event just outside the raw
    # horizon still casts its buffer onto the last in-horizon day.
    hard_blocked = _hard_blocked_dates(
        activity_rows, today - timedelta(days=1), horizon_end + timedelta(days=1)
    )

    moves = plan_reschedule_moves(missed, occupied, hard_blocked, today)
    for pw, new_date in moves:
        pw.rescheduled_from = pw.scheduled_date
        pw.scheduled_date = new_date
    if moves:
        db.commit()
        for pw, _ in moves:
            db.refresh(pw)
    return [pw for pw, _ in moves]
