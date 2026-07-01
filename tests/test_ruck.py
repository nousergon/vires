"""Ruck (loaded-cardio) quick-log endpoint — Tier 0."""

from __future__ import annotations

_LB_TO_KG = 0.45359237


def test_log_ruck_converts_to_si_and_computes_load(client):
    # Default account unit is 'lb' ⇒ distance in miles, elevation in feet.
    r = client.post(
        "/api/workouts/ruck",
        json={
            "pack_weight": 45,
            "bodyweight": 180,
            "distance": 3,  # miles
            "elevation_gain": 1000,  # feet
            "duration_s": 3600,
            "terrain": "trail",
            "name": "Morning ruck",
        },
    )
    assert r.status_code == 201
    ws = r.json()
    assert ws["session_type"] == "ruck"
    assert ws["name"] == "Morning ruck"
    assert ws["ended_at"] is not None  # quick-log records a completed activity
    assert ws["exercises"] == []

    ruck = ws["ruck"]
    assert ruck is not None
    assert abs(ruck["pack_weight_kg"] - 45 * _LB_TO_KG) < 1e-6
    assert abs(ruck["bodyweight_kg"] - 180 * _LB_TO_KG) < 1e-6
    assert abs(ruck["distance_m"] - 3 * 1609.344) < 1e-3
    assert abs(ruck["elevation_gain_m"] - 1000 * 0.3048) < 1e-3
    assert ruck["source"] == "manual"
    assert ruck["metabolic_cost_kj"] is not None and ruck["metabolic_cost_kj"] > 0


def test_log_ruck_metric_unit_no_conversion(client):
    client.put("/api/settings", json={"weight_unit": "kg"})
    r = client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 20, "bodyweight": 82, "distance": 8, "duration_s": 5400},
    )
    assert r.status_code == 201
    ruck = r.json()["ruck"]
    assert ruck["pack_weight_kg"] == 20  # kg in, kg stored — no conversion
    assert ruck["distance_m"] == 8 * 1000.0  # km ⇒ m


def test_ruck_without_distance_has_no_load(client):
    r = client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 40, "bodyweight": 175},  # no distance/duration
    )
    assert r.status_code == 201
    ruck = r.json()["ruck"]
    assert ruck["metabolic_cost_kj"] is None  # honest N/A, not a fabricated 0


def test_ruck_appears_in_history_list(client):
    client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 35, "bodyweight": 170, "distance": 5, "duration_s": 4200},
    )
    rows = client.get("/api/workouts").json()
    ruck_rows = [w for w in rows if w["session_type"] == "ruck"]
    assert len(ruck_rows) == 1
    assert ruck_rows[0]["ruck"]["metabolic_cost_kj"] is not None
    # A ruck carries no exercises/sets/volume.
    assert ruck_rows[0]["exercise_count"] == 0
    assert ruck_rows[0]["set_count"] == 0


def test_ruck_rejects_nonpositive_weights(client):
    r = client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 0, "bodyweight": 180, "distance": 3, "duration_s": 3600},
    )
    assert r.status_code == 422  # pack_weight must be > 0


def test_ruck_records_input_source(client):
    # A derived-mode log (e.g. GPX import) tags its source; default stays 'manual'.
    r = client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 40, "bodyweight": 180, "distance": 5, "source": "gpx"},
    )
    assert r.status_code == 201
    assert r.json()["ruck"]["source"] == "gpx"
    dflt = client.post("/api/workouts/ruck", json={"pack_weight": 40, "bodyweight": 180}).json()
    assert dflt["ruck"]["source"] == "manual"


def test_ruck_rejects_unknown_source(client):
    r = client.post(
        "/api/workouts/ruck",
        json={"pack_weight": 40, "bodyweight": 180, "source": "strava"},
    )
    assert r.status_code == 422  # not in the RuckSource literal


def test_heavier_pack_logs_higher_load(client):
    common = {"bodyweight": 180, "distance": 5, "elevation_gain": 500, "duration_s": 4500}
    light = client.post(
        "/api/workouts/ruck", json={**common, "pack_weight": 10}
    ).json()["ruck"]["metabolic_cost_kj"]
    heavy = client.post(
        "/api/workouts/ruck", json={**common, "pack_weight": 50}
    ).json()["ruck"]["metabolic_cost_kj"]
    assert heavy > light
