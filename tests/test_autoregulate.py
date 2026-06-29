"""Deterministic autoregulation assessment (pure, no DB).

Covers the double-progression verdict in
``api.services.coach.autoregulate.assess_exercise``.
"""

from __future__ import annotations

from api.services.coach.autoregulate import (
    DURATION_STEP_SECONDS,
    ExercisePerformance,
    SetResult,
    assess_exercise,
)


def _weighted(
    *,
    target_sets=3,
    target_reps=10,
    target_weight=100.0,
    sets,
) -> ExercisePerformance:
    return ExercisePerformance(
        exercise_id=1,
        is_timed=False,
        target_sets=target_sets,
        target_reps=target_reps,
        target_weight=target_weight,
        target_duration_seconds=None,
        sets=sets,
    )


def _s(reps=None, weight=None, dur=None, completed=True) -> SetResult:
    return SetResult(reps=reps, weight=weight, duration_seconds=dur, completed=completed)


# --------------------------------------------------------------------------- #
# weighted: double progression
# --------------------------------------------------------------------------- #
def test_hit_all_sets_at_target_progresses_one_plate_lb():
    perf = _weighted(sets=[_s(10, 100), _s(10, 100), _s(10, 100)])
    adj = assess_exercise(perf, "lb")
    assert adj.verdict == "progress" and adj.weight_delta == 2.5


def test_progress_uses_kg_plate_for_kg_unit():
    perf = _weighted(sets=[_s(10, 100), _s(10, 100), _s(10, 100)])
    assert assess_exercise(perf, "kg").weight_delta == 1.25


def test_exceeding_reps_still_progresses():
    perf = _weighted(sets=[_s(12, 100), _s(11, 100), _s(10, 100)])
    assert assess_exercise(perf, "lb").verdict == "progress"


def test_missed_a_set_backs_off():
    # only 2 of 3 prescribed sets completed
    perf = _weighted(sets=[_s(10, 100), _s(10, 100), _s(10, 100, completed=False)])
    adj = assess_exercise(perf, "lb")
    assert adj.verdict == "back_off" and adj.weight_delta == -2.5


def test_two_reps_short_at_target_weight_backs_off():
    perf = _weighted(sets=[_s(8, 100), _s(8, 100), _s(8, 100)])
    assert assess_exercise(perf, "lb").verdict == "back_off"


def test_one_rep_short_holds_no_yoyo():
    perf = _weighted(sets=[_s(9, 100), _s(9, 100), _s(10, 100)])
    assert assess_exercise(perf, "lb").verdict == "hold"


def test_scaled_down_weight_holds():
    # used lighter weight than prescribed — self-regulated; don't auto-progress
    perf = _weighted(sets=[_s(10, 90), _s(10, 90), _s(10, 90)])
    assert assess_exercise(perf, "lb").verdict == "hold"


def test_no_completed_sets_holds():
    perf = _weighted(sets=[_s(10, 100, completed=False)])
    assert assess_exercise(perf, "lb").verdict == "hold"


def test_missing_targets_holds():
    perf = _weighted(target_reps=None, target_weight=None, sets=[_s(10, 100)])
    assert assess_exercise(perf, "lb").verdict == "hold"


# --------------------------------------------------------------------------- #
# timed exercises
# --------------------------------------------------------------------------- #
def _timed(*, target_sets=3, target_duration=30, sets) -> ExercisePerformance:
    return ExercisePerformance(
        exercise_id=2,
        is_timed=True,
        target_sets=target_sets,
        target_reps=None,
        target_weight=None,
        target_duration_seconds=target_duration,
        sets=sets,
    )


def test_timed_holds_all_sets_progresses_duration():
    perf = _timed(sets=[_s(dur=30), _s(dur=32), _s(dur=30)])
    adj = assess_exercise(perf, "lb")
    assert adj.verdict == "progress"
    assert adj.duration_delta_seconds == DURATION_STEP_SECONDS


def test_timed_missed_set_backs_off_duration():
    perf = _timed(sets=[_s(dur=30), _s(dur=30), _s(dur=30, completed=False)])
    adj = assess_exercise(perf, "lb")
    assert adj.verdict == "back_off"
    assert adj.duration_delta_seconds == -DURATION_STEP_SECONDS
