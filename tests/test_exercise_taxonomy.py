"""Unit tests for the movement-pattern classifier (no DB needed)."""

from __future__ import annotations

from api.db.exercise_taxonomy import infer_movement_pattern


def _classify(name: str, **kwargs) -> str:
    return infer_movement_pattern(name=name, **kwargs)


def test_hinge_family():
    assert _classify("Romanian Deadlift", primary_muscles=["hamstrings"]) == "hinge"
    assert _classify("Trap Bar Deadlift", primary_muscles=["hamstrings"]) == "hinge"
    assert _classify("Good Morning", primary_muscles=["hamstrings"]) == "hinge"


def test_squat_family():
    assert _classify("Barbell Squat", primary_muscles=["quadriceps"]) == "squat"
    assert _classify("Front Squats With Two Kettlebells", primary_muscles=["quadriceps"]) == "squat"
    assert _classify("Narrow Stance Squats", primary_muscles=["quadriceps"]) == "squat"


def test_static_hold_via_is_timed():
    assert _classify("Plank", primary_muscles=["abdominals"], is_timed=True) == "static_hold"


def test_static_hold_via_name_for_provisional_exercise():
    # is_timed defaults False for a freshly user-created exercise, so a
    # hold/isometric name still needs to route to static_hold.
    assert _classify("Hollow Body Hold", primary_muscles=["abdominals"]) == "static_hold"


def test_vertical_vs_horizontal_push():
    assert _classify("Standing Military Press", primary_muscles=["shoulders"]) == "vertical_push"
    assert (
        _classify("Barbell Bench Press - Medium Grip", primary_muscles=["chest"])
        == "horizontal_push"
    )


def test_vertical_vs_horizontal_pull():
    assert _classify("Pullups", primary_muscles=["lats"]) == "vertical_pull"
    assert _classify("Bent Over Barbell Row", primary_muscles=["middle back"]) == "horizontal_pull"


def test_cardio_and_mobility_categories():
    assert _classify("Anything", category="cardio") == "cardio"
    assert _classify("Anything Else", category="stretching") == "mobility"


def test_unclassifiable_falls_back_to_other():
    assert _classify("Iron Cross", category="strength", primary_muscles=["shoulders"]) == "other"
