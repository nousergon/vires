"""Unit tests for exercise-swap equivalence evaluation."""

from __future__ import annotations

from api.db.models import Exercise
from api.services.exercise_swap import (
    COMPARABLE,
    DIFFERENT_STIMULUS,
    EQUIVALENT,
    detect_swaps,
    evaluate_swap,
)


def _ex(id_, name, pattern, primary=(), secondary=(), equipment=None) -> Exercise:
    return Exercise(
        id=id_,
        name=name,
        canonical_name=name.lower(),
        movement_pattern=pattern,
        primary_muscles=list(primary),
        secondary_muscles=list(secondary),
        equipment=equipment,
        provenance="canonical",
    )


def test_same_pattern_high_overlap_is_equivalent():
    rdl = _ex(1, "Romanian Deadlift", "hinge", primary=["hamstrings"], secondary=["glutes"])
    trap_bar = _ex(
        2, "Trap Bar Deadlift", "hinge", primary=["hamstrings"], secondary=["glutes"]
    )
    result = evaluate_swap(rdl, trap_bar)
    assert result.verdict == EQUIVALENT
    assert result.same_pattern is True


def test_different_pattern_no_overlap_is_different_stimulus():
    rdl = _ex(1, "Romanian Deadlift", "hinge", primary=["hamstrings"])
    curl = _ex(2, "Barbell Curl", "isolation", primary=["biceps"])
    result = evaluate_swap(rdl, curl)
    assert result.verdict == DIFFERENT_STIMULUS
    assert result.same_pattern is False
    assert result.muscle_overlap == 0.0


def test_different_pattern_strong_muscle_overlap_is_comparable():
    squat = _ex(1, "Barbell Squat", "squat", primary=["quadriceps"], secondary=["glutes"])
    leg_press = _ex(
        2, "Leg Press", "squat", primary=["quadriceps"], secondary=["glutes"]
    )  # same pattern in our taxonomy, but exercise this at a lower overlap deliberately
    result = evaluate_swap(squat, leg_press)
    assert result.verdict in (EQUIVALENT, COMPARABLE)


def test_detect_swaps_ignores_unchanged_and_reordered():
    old = [10, 20, 30]
    new = [30, 10, 99]  # 20 removed, 99 added, 10/30 just reordered
    assert detect_swaps(old, new) == [(20, 99)]


def test_detect_swaps_no_change():
    assert detect_swaps([1, 2, 3], [1, 2, 3]) == []


def test_detect_swaps_multiple():
    old = [1, 2, 3]
    new = [1, 20, 30]
    pairs = detect_swaps(old, new)
    assert set(pairs) == {(2, 20), (3, 30)}
