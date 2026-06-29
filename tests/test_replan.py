"""Macro re-plan trigger detection (pure, no DB).

Covers ``api.services.coach.replan.evaluate_triggers``.
"""

from __future__ import annotations

from datetime import date

from api.db.models import Objective, PlannedWorkout
from api.services.coach.replan import evaluate_triggers

TODAY = date(2026, 6, 29)
PAST = date(2026, 6, 1)
FUTURE = date(2026, 7, 6)


def _pw(scheduled_date: date, status: str = "planned") -> PlannedWorkout:
    return PlannedWorkout(scheduled_date=scheduled_date, status=status)


def _obj(id: int, *, kind: str = "dated", target_date: date | None = None) -> Objective:
    return Objective(id=id, name=f"o{id}", kind=kind, target_date=target_date)


def _kinds(planned, program_objective=None, focus_objective=None):
    return {
        t.kind
        for t in evaluate_triggers(
            planned,
            program_objective=program_objective,
            focus_objective=focus_objective,
            today=TODAY,
        )
    }


def test_fresh_plan_fires_nothing():
    obj = _obj(1, target_date=FUTURE)
    assert _kinds([_pw(FUTURE)], program_objective=obj, focus_objective=obj) == set()


def test_two_missed_sessions_fire():
    obj = _obj(1, target_date=FUTURE)
    kinds = _kinds([_pw(PAST), _pw(PAST), _pw(FUTURE)], obj, obj)
    assert kinds == {"missed_sessions"}


def test_one_missed_is_below_threshold():
    obj = _obj(1, target_date=FUTURE)
    assert _kinds([_pw(PAST), _pw(FUTURE)], obj, obj) == set()


def test_no_future_planned_is_exhausted():
    obj = _obj(1, target_date=FUTURE)
    # the only past day is completed, so it's exhausted (not "missed")
    assert _kinds([_pw(PAST, "completed")], obj, obj) == {"plan_exhausted"}


def test_objective_passed_fires():
    obj = _obj(1, target_date=PAST)
    assert _kinds([_pw(FUTURE)], obj, obj) == {"objective_passed"}


def test_objective_changed_fires_when_focus_differs():
    built_for = _obj(1, target_date=FUTURE)
    now_focus = _obj(2, target_date=FUTURE)
    assert _kinds([_pw(FUTURE)], built_for, now_focus) == {"objective_changed"}


def test_no_objective_either_side_is_no_change():
    assert _kinds([_pw(FUTURE)], program_objective=None, focus_objective=None) == set()


def test_multiple_triggers_stack():
    built_for = _obj(1, target_date=PAST)  # passed
    now_focus = _obj(2, target_date=FUTURE)  # and changed
    # all past + planned -> missed + exhausted too
    kinds = _kinds([_pw(PAST), _pw(PAST)], built_for, now_focus)
    assert kinds == {
        "missed_sessions",
        "plan_exhausted",
        "objective_passed",
        "objective_changed",
    }
