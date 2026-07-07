"""Macro re-plan trigger detection (pure, no DB).

Covers ``api.services.coach.replan.evaluate_triggers``.
"""

from __future__ import annotations

from datetime import date

from api.db.models import Objective, PlannedWorkout
from api.services.coach.objective_context import AilmentCheckInCtx, AilmentEpisodeCtx
from api.services.coach.replan import evaluate_triggers

TODAY = date(2026, 6, 29)
PAST = date(2026, 6, 1)
FUTURE = date(2026, 7, 6)
# Well outside the "just registered" window relative to TODAY, so onset alone
# doesn't fire the trigger in the severity/delta-focused tests below.
OLD_ONSET = date(2026, 6, 1)


def _pw(scheduled_date: date, status: str = "planned") -> PlannedWorkout:
    return PlannedWorkout(scheduled_date=scheduled_date, status=status)


def _ailment(
    *,
    label: str = "Right knee",
    status: str = "active",
    onset_date: date = OLD_ONSET,
    check_ins: list[AilmentCheckInCtx] | None = None,
) -> AilmentEpisodeCtx:
    check_ins = check_ins or []
    latest = max(check_ins, key=lambda c: c.check_in_date, default=None)
    return AilmentEpisodeCtx(
        label=label,
        onset_date=onset_date,
        status=status,
        latest_severity=latest.severity if latest else None,
        latest_check_in_date=latest.check_in_date if latest else None,
        check_ins=check_ins,
    )


def _check_in(d: date, severity: int) -> AilmentCheckInCtx:
    return AilmentCheckInCtx(check_in_date=d, severity=severity)


def _obj(
    id: int,
    *,
    kind: str = "dated",
    target_date: date | None = None,
    event_end_date: date | None = None,
) -> Objective:
    return Objective(
        id=id, name=f"o{id}", kind=kind,
        target_date=target_date, event_end_date=event_end_date,
    )


def _kinds(
    planned, program_objective=None, focus_objective=None, program_objectives=None, ailments=()
):
    objs = program_objectives if program_objectives is not None else (
        [program_objective] if program_objective is not None else []
    )
    return {
        t.kind
        for t in evaluate_triggers(
            planned,
            program_objectives=objs,
            focus_objective=focus_objective,
            today=TODAY,
            ailments=ailments,
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


# --------------------------------------------------------------------------- #
# season-aware (multiple program objectives)
# --------------------------------------------------------------------------- #
def test_passed_block_fires_while_a_later_block_remains():
    baker = _obj(1, target_date=PAST)  # block done
    kt = _obj(2, target_date=FUTURE)  # still ahead
    # focus is the upcoming KT (a program objective) -> no objective_changed;
    # KT block still has future workouts -> not exhausted
    kinds = _kinds([_pw(FUTURE)], program_objectives=[baker, kt], focus_objective=kt)
    assert kinds == {"objective_passed"}


def test_block_on_a_multi_day_event_is_not_yet_passed():
    # peak was yesterday but the trip runs through next week -> block not done
    on_trip = _obj(1, target_date=date(2026, 6, 28), event_end_date=date(2026, 7, 3))
    kinds = _kinds([_pw(FUTURE)], program_objectives=[on_trip], focus_objective=on_trip)
    assert "objective_passed" not in kinds


def test_new_objective_outside_the_season_fires_changed():
    baker = _obj(1, target_date=FUTURE)
    kt = _obj(2, target_date=FUTURE)
    brand_new = _obj(3, target_date=FUTURE)  # added after the plan was built
    kinds = _kinds(
        [_pw(FUTURE)], program_objectives=[baker, kt], focus_objective=brand_new
    )
    assert kinds == {"objective_changed"}


# --------------------------------------------------------------------------- #
# ailment_changed (vires-ops#50)
# --------------------------------------------------------------------------- #
def test_severity_seven_check_in_fires_ailment_changed():
    # A single check-in at 7/10 — already at/above the severity threshold (6).
    ep = _ailment(check_ins=[_check_in(date(2026, 6, 20), 7)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == {"ailment_changed"}


def test_mild_severity_does_not_fire():
    ep = _ailment(check_ins=[_check_in(date(2026, 6, 20), 2), _check_in(date(2026, 6, 21), 3)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == set()


def test_severity_jump_of_three_or_more_fires_even_below_threshold():
    # 2 -> 5 is a jump of 3, but 5 is still below the absolute severity threshold.
    ep = _ailment(check_ins=[_check_in(date(2026, 6, 20), 2), _check_in(date(2026, 6, 27), 5)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == {"ailment_changed"}


def test_severity_jump_of_two_does_not_fire():
    ep = _ailment(check_ins=[_check_in(date(2026, 6, 20), 2), _check_in(date(2026, 6, 27), 4)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == set()


def test_newly_registered_ailment_fires():
    ep = _ailment(onset_date=TODAY, check_ins=[_check_in(TODAY, 3)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == {"ailment_changed"}


def test_resolved_ailment_does_not_fire():
    ep = _ailment(status="resolved", check_ins=[_check_in(date(2026, 6, 20), 9)])
    kinds = _kinds([_pw(FUTURE)], ailments=[ep])
    assert kinds == set()


def test_ailment_trigger_stacks_with_structural_triggers():
    obj = _obj(1, target_date=FUTURE)
    ep = _ailment(check_ins=[_check_in(date(2026, 6, 20), 7)])
    kinds = _kinds(
        [_pw(PAST), _pw(PAST), _pw(FUTURE)],
        program_objective=obj,
        focus_objective=obj,
        ailments=[ep],
    )
    assert kinds == {"missed_sessions", "ailment_changed"}
