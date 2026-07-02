"""Auto-reschedule-missed-workouts placement logic (pure, no DB).

Covers ``api.services.reschedule.plan_reschedule_moves`` and
``_hard_blocked_dates``.
"""

from __future__ import annotations

from datetime import date, timedelta

from api.db.models import CalendarEvent, PlannedWorkout, Program
from api.services.reschedule import (
    DEFAULT_HORIZON_DAYS,
    _hard_blocked_dates,
    plan_reschedule_moves,
)

TODAY = date(2026, 7, 3)  # a Friday, matching Brian's actual scenario


def _pw(id: int, scheduled_date: date, *, program: Program | None = None) -> PlannedWorkout:
    pw = PlannedWorkout(scheduled_date=scheduled_date, status="planned")
    pw.id = id
    if program is not None:
        pw.program_id = 1
        pw.program = program
    return pw


def _event(
    event_date: date, intensity: str | None, *, event_end_date: date | None = None
) -> CalendarEvent:
    load = {"regions": "legs", "intensity": intensity, "duration_min": None} if intensity else None
    return CalendarEvent(
        event_date=event_date,
        event_end_date=event_end_date,
        recurrence="none",
        load=load,
    )


# --------------------------------------------------------------------------- #
# basic placement
# --------------------------------------------------------------------------- #
def test_moves_to_today_when_open():
    missed = _pw(1, TODAY - timedelta(days=1))
    moves = plan_reschedule_moves([missed], set(), set(), TODAY)
    assert len(moves) == 1
    assert moves[0] == (missed, TODAY)


def test_moves_to_next_day_when_today_occupied():
    occupied = {TODAY}
    moves = plan_reschedule_moves([_pw(1, TODAY - timedelta(days=1))], occupied, set(), TODAY)
    assert moves[0][1] == TODAY + timedelta(days=1)


def test_two_missed_oldest_first_no_collision():
    older = _pw(1, TODAY - timedelta(days=3))
    newer = _pw(2, TODAY - timedelta(days=1))
    moves = plan_reschedule_moves([newer, older], set(), set(), TODAY)
    by_id = {pw.id: d for pw, d in moves}
    # older is processed first and claims the earliest day; newer gets bumped.
    assert by_id[1] == TODAY
    assert by_id[2] == TODAY + timedelta(days=1)


def test_horizon_exhausted_leaves_workout_untouched():
    occupied = {TODAY + timedelta(days=i) for i in range(DEFAULT_HORIZON_DAYS + 1)}
    moves = plan_reschedule_moves([_pw(1, TODAY - timedelta(days=1))], occupied, set(), TODAY)
    assert moves == []


def test_program_end_date_caps_horizon():
    program = Program(end_date=TODAY + timedelta(days=2))
    occupied = {TODAY, TODAY + timedelta(days=1), TODAY + timedelta(days=2)}
    moves = plan_reschedule_moves(
        [_pw(1, TODAY - timedelta(days=1), program=program)], occupied, set(), TODAY
    )
    # every day within the program's horizon is occupied -> no move, even
    # though the flat 13-day default would have found room later.
    assert moves == []


def test_ties_broken_by_id():
    same_date = TODAY - timedelta(days=2)
    lower = _pw(1, same_date)
    higher = _pw(2, same_date)
    moves = plan_reschedule_moves([higher, lower], set(), set(), TODAY)
    by_id = {pw.id: d for pw, d in moves}
    assert by_id[1] == TODAY
    assert by_id[2] == TODAY + timedelta(days=1)


# --------------------------------------------------------------------------- #
# hard-event buffer (Brian's own examples)
# --------------------------------------------------------------------------- #
def test_hard_event_day_and_neighbors_never_valid():
    hike_day = TODAY + timedelta(days=2)
    events = [_event(hike_day, "hard")]
    blocked = _hard_blocked_dates(events, TODAY - timedelta(days=1), TODAY + timedelta(days=13))
    assert hike_day - timedelta(days=1) in blocked
    assert hike_day in blocked
    assert hike_day + timedelta(days=1) in blocked
    assert hike_day - timedelta(days=2) not in blocked
    assert hike_day + timedelta(days=2) not in blocked


def test_multiday_hard_event_buffer_wraps_whole_span():
    start = TODAY + timedelta(days=3)
    end = start + timedelta(days=2)
    events = [_event(start, "hard", event_end_date=end)]
    blocked = _hard_blocked_dates(events, TODAY - timedelta(days=1), TODAY + timedelta(days=13))
    assert start - timedelta(days=1) in blocked
    for d in (start, start + timedelta(days=1), end):
        assert d in blocked
    assert end + timedelta(days=1) in blocked
    assert start - timedelta(days=2) not in blocked
    assert end + timedelta(days=2) not in blocked


def test_moderate_event_imposes_no_buffer():
    event_day = TODAY + timedelta(days=2)
    events = [_event(event_day, "moderate")]
    blocked = _hard_blocked_dates(events, TODAY - timedelta(days=1), TODAY + timedelta(days=13))
    assert blocked == set()


def test_event_with_no_load_imposes_no_buffer():
    events = [_event(TODAY + timedelta(days=2), None)]
    blocked = _hard_blocked_dates(events, TODAY - timedelta(days=1), TODAY + timedelta(days=13))
    assert blocked == set()


def test_hard_event_disqualifies_an_otherwise_open_day_end_to_end():
    # Missed Thursday; a hard hike lands exactly on the day it would
    # otherwise claim first — its buffer blocks today-1, today, and today+1.
    missed = _pw(1, TODAY - timedelta(days=1))
    events = [_event(TODAY, "hard")]
    blocked = _hard_blocked_dates(events, TODAY - timedelta(days=1), TODAY + timedelta(days=13))
    moves = plan_reschedule_moves([missed], set(), blocked, TODAY)
    assert moves[0][1] == TODAY + timedelta(days=2)


# --------------------------------------------------------------------------- #
# soft preference: spacing from other planned workouts (forward-only — two
# ordinary lifting days back-to-back is fine; landing right BEFORE an
# already-fixed one is what's worth avoiding)
# --------------------------------------------------------------------------- #
def test_prefers_a_later_day_over_one_landing_right_before_a_planned_workout():
    # Mirrors Brian's Saturday-vs-Sunday example: today (Friday) already has
    # its own workout, and Monday (today+3) already has a workout too, so
    # Sunday (today+2, immediately before Monday) is soft-penalized in favor
    # of Saturday (today+1) even though Sunday is hard-valid too.
    monday = TODAY + timedelta(days=3)
    occupied = {TODAY, monday}
    missed = _pw(1, TODAY - timedelta(days=1))
    moves = plan_reschedule_moves([missed], occupied, set(), TODAY)
    assert moves[0][1] == TODAY + timedelta(days=1)  # Saturday, not Sunday


def test_landing_right_after_a_planned_workout_is_never_penalized():
    # Back-to-back ordinary lifting days (landing right AFTER an occupied
    # day) is a normal split, not penalized — only landing right BEFORE one
    # is. today is occupied; today+1 should still be chosen directly.
    occupied = {TODAY}
    missed = _pw(1, TODAY - timedelta(days=1))
    moves = plan_reschedule_moves([missed], occupied, set(), TODAY)
    assert moves[0][1] == TODAY + timedelta(days=1)


def test_falls_back_to_penalized_day_when_every_valid_day_is_penalized():
    # Bounded horizon via a program end_date; every open day's very next day
    # is occupied, so every hard-valid candidate is soft-penalized. Still
    # lands on the earliest one rather than going unscheduled.
    program = Program(end_date=TODAY + timedelta(days=4))
    occupied = {
        TODAY + timedelta(days=1),
        TODAY + timedelta(days=3),
        TODAY + timedelta(days=5),  # beyond the horizon, still penalizes today+4
    }
    missed = _pw(1, TODAY - timedelta(days=1), program=program)
    moves = plan_reschedule_moves([missed], occupied, set(), TODAY)
    assert moves[0][1] == TODAY  # earliest hard-valid day, used as a fallback
