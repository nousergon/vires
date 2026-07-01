"""Pandolf load-carriage metabolic model — unit tests."""

from __future__ import annotations

import pytest

from api.services.load.pandolf import (
    pandolf_metabolic_watts,
    ruck_metabolic_cost_kj,
    terrain_factor,
)


def test_terrain_factor_defaults_and_lookup():
    assert terrain_factor("treadmill") == 1.0
    assert terrain_factor("trail") == 1.2
    assert terrain_factor("snow") == 1.7
    # Unknown / None fall back to the trail default rather than raising.
    assert terrain_factor(None) == 1.2
    assert terrain_factor("bogus") == 1.2


def test_metabolic_watts_reference_point():
    # 70 kg body, 30 kg load, 1.34 m/s (~3 mph), level, treadmill (η=1).
    # Hand-computed from Pandolf (1977): 105 + 36.7 + 269.3 ≈ 411 W.
    w = pandolf_metabolic_watts(
        bodyweight_kg=70, load_kg=30, speed_ms=1.34, grade_pct=0, eta=1.0
    )
    assert 405 < w < 418


def test_load_and_grade_monotonicity():
    base = dict(bodyweight_kg=75, speed_ms=1.3, eta=1.2)
    light = pandolf_metabolic_watts(load_kg=10, grade_pct=0, **base)
    heavy = pandolf_metabolic_watts(load_kg=30, grade_pct=0, **base)
    steep = pandolf_metabolic_watts(load_kg=30, grade_pct=10, **base)
    # Heavier pack costs more; climbing costs more than flat.
    assert heavy > light
    assert steep > heavy


def test_standing_floor_never_negative_locomotion():
    # Very low speed, level ground: cost must not fall below the standing floor.
    w = pandolf_metabolic_watts(
        bodyweight_kg=70, load_kg=25, speed_ms=0.3, grade_pct=0, eta=1.0
    )
    standing = 1.5 * 70 + 2.0 * (70 + 25) * (25 / 70) ** 2
    assert w >= standing


def test_zero_bodyweight_raises():
    with pytest.raises(ValueError):
        pandolf_metabolic_watts(bodyweight_kg=0, load_kg=20, speed_ms=1.3, grade_pct=0, eta=1.0)


def test_cost_kj_none_without_distance_or_duration():
    common = dict(bodyweight_kg=80, pack_weight_kg=20, elevation_gain_m=100, terrain="trail")
    assert ruck_metabolic_cost_kj(distance_m=None, duration_s=3600, **common) is None
    assert ruck_metabolic_cost_kj(distance_m=5000, duration_s=None, **common) is None
    assert ruck_metabolic_cost_kj(distance_m=0, duration_s=3600, **common) is None


def test_cost_kj_heavier_pack_costs_more():
    common = dict(
        bodyweight_kg=80, distance_m=8000, elevation_gain_m=300, duration_s=5400, terrain="trail"
    )
    light = ruck_metabolic_cost_kj(pack_weight_kg=5, **common)
    heavy = ruck_metabolic_cost_kj(pack_weight_kg=25, **common)
    assert light is not None and heavy is not None
    assert heavy > light
