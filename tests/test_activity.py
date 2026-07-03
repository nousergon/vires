"""Activity quick-log endpoint (cross-training + locomotion) — Tier 0."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_LB_TO_KG = 0.45359237


def test_log_activity_from_template(client):
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Indoor top-rope",
            "template_key": "climbing_indoor_toprope",
            "duration_s": 5400,
            "regions": "upper",
            "intensity": "moderate",
        },
    )
    assert r.status_code == 201
    ws = r.json()
    assert ws["session_type"] == "activity"
    assert ws["name"] == "Indoor top-rope"
    assert ws["ended_at"] is not None  # quick-log records a completed activity
    assert ws["exercises"] == []

    activity = ws["activity"]
    assert activity is not None
    assert activity["template_key"] == "climbing_indoor_toprope"
    assert activity["duration_s"] == 5400
    assert activity["regions"] == "upper"
    assert activity["intensity"] == "moderate"


def test_log_activity_custom_freeform(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Ultimate frisbee", "regions": "legs", "intensity": "hard"},
    )
    assert r.status_code == 201
    activity = r.json()["activity"]
    assert activity["template_key"] == "custom"  # default when omitted
    assert activity["duration_s"] is None
    assert activity["regions"] == "legs"
    assert activity["intensity"] == "hard"


def test_log_activity_requires_name(client):
    r = client.post("/api/workouts/activity", json={"regions": "full", "intensity": "light"})
    assert r.status_code == 422


def test_log_activity_rejects_unknown_region(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Mystery sport", "regions": "arms", "intensity": "moderate"},
    )
    assert r.status_code == 422  # not in the LoadRegions literal


def test_log_activity_backdates_to_a_past_date(client):
    yesterday = datetime.now(UTC) - timedelta(days=1)
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Yoga",
            "regions": "full",
            "intensity": "light",
            "started_at": yesterday.isoformat(),
        },
    )
    assert r.status_code == 201
    ws = r.json()
    assert datetime.fromisoformat(ws["started_at"]).date() == yesterday.date()


def test_activity_appears_in_history_list(client):
    client.post(
        "/api/workouts/activity",
        json={
            "name": "Swim",
            "template_key": "swimming",
            "regions": "full",
            "intensity": "moderate",
        },
    )
    rows = client.get("/api/workouts").json()
    activity_rows = [w for w in rows if w["session_type"] == "activity"]
    assert len(activity_rows) == 1
    assert activity_rows[0]["activity"]["template_key"] == "swimming"
    # A generic activity carries no exercises/sets/volume.
    assert activity_rows[0]["exercise_count"] == 0
    assert activity_rows[0]["set_count"] == 0


def test_activity_templates_catalog_is_nonempty_and_shaped(client):
    r = client.get("/api/workouts/activity-templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) > 0
    by_key = {t["key"]: t for t in templates}
    assert "climbing_indoor_toprope" in by_key
    for key in ("walk", "run", "hike"):
        assert by_key[key]["route_capable"] is True
    for key in ("climbing_indoor_toprope", "swimming", "yoga"):
        assert by_key[key]["route_capable"] is False
    for t in templates:
        assert t["regions"] in {"legs", "upper", "full", "core", "none"}
        assert t["intensity"] in {"light", "moderate", "hard"}
        assert isinstance(t["route_capable"], bool)


# --------------------------------------------------------------------------- #
# Route + optional pack weight (formerly the standalone "ruck" endpoint,
# merged 2026-07-02 — see alembic merge_ruck_into_activity migration).
# --------------------------------------------------------------------------- #
def test_log_hike_with_pack_converts_to_si_and_computes_load(client):
    # Default account unit is 'lb' ⇒ distance in miles, elevation in feet.
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Morning hike",
            "template_key": "hike",
            "pack_weight": 45,
            "bodyweight": 180,
            "distance": 3,  # miles
            "elevation_gain": 1000,  # feet
            "duration_s": 3600,
            "terrain": "trail",
        },
    )
    assert r.status_code == 201
    ws = r.json()
    assert ws["session_type"] == "activity"
    assert ws["name"] == "Morning hike"
    assert ws["ended_at"] is not None
    assert ws["exercises"] == []

    activity = ws["activity"]
    assert activity is not None
    assert activity["template_key"] == "hike"
    assert abs(activity["pack_weight_kg"] - 45 * _LB_TO_KG) < 1e-6
    assert abs(activity["bodyweight_kg"] - 180 * _LB_TO_KG) < 1e-6
    assert abs(activity["distance_m"] - 3 * 1609.344) < 1e-3
    assert abs(activity["elevation_gain_m"] - 1000 * 0.3048) < 1e-3
    assert activity["source"] == "manual"
    assert activity["metabolic_cost_kj"] is not None and activity["metabolic_cost_kj"] > 0


def test_log_hike_metric_unit_no_conversion(client):
    client.put("/api/settings", json={"weight_unit": "kg"})
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Hike",
            "template_key": "hike",
            "pack_weight": 20,
            "bodyweight": 82,
            "distance": 8,
            "duration_s": 5400,
        },
    )
    assert r.status_code == 201
    activity = r.json()["activity"]
    assert activity["pack_weight_kg"] == 20  # kg in, kg stored — no conversion
    assert activity["distance_m"] == 8 * 1000.0  # km ⇒ m


def test_loaded_activity_without_distance_has_no_load(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Hike", "template_key": "hike", "pack_weight": 40, "bodyweight": 175},
    )
    assert r.status_code == 201
    activity = r.json()["activity"]
    assert activity["metabolic_cost_kj"] is None  # honest N/A, not a fabricated 0


def test_walk_with_no_pack_never_computes_a_load_number(client):
    # Pack weight is optional on every template — an unloaded walk/run/hike
    # never computes a metabolic cost at all, not even a synthetic 0.
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Evening walk",
            "template_key": "walk",
            "distance": 2,
            "duration_s": 1800,
        },
    )
    assert r.status_code == 201
    activity = r.json()["activity"]
    assert activity["pack_weight_kg"] is None
    assert activity["metabolic_cost_kj"] is None


def test_run_appears_in_history_with_route_and_no_pack(client):
    client.post(
        "/api/workouts/activity",
        json={"name": "Tempo run", "template_key": "run", "distance": 5, "duration_s": 1500},
    )
    rows = client.get("/api/workouts").json()
    run_rows = [w for w in rows if w["activity"] and w["activity"]["template_key"] == "run"]
    assert len(run_rows) == 1
    assert run_rows[0]["activity"]["pack_weight_kg"] is None
    assert run_rows[0]["activity"]["distance_m"] is not None
    # A locomotion activity carries no exercises/sets/volume.
    assert run_rows[0]["exercise_count"] == 0
    assert run_rows[0]["set_count"] == 0


def test_pack_weight_without_bodyweight_is_rejected(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Hike", "template_key": "hike", "pack_weight": 40, "distance": 3},
    )
    assert r.status_code == 422  # Pandolf's load ratio is undefined without bodyweight


def test_bodyweight_without_pack_weight_is_accepted_and_ignored(client):
    # Bodyweight alone (no pack) isn't required/used for anything — the
    # validator only fires pack-without-bodyweight, not the reverse.
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Walk", "template_key": "walk", "bodyweight": 180, "distance": 2},
    )
    assert r.status_code == 201
    activity = r.json()["activity"]
    assert activity["pack_weight_kg"] is None
    assert activity["metabolic_cost_kj"] is None


def test_activity_rejects_zero_pack_weight(client):
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Hike",
            "template_key": "hike",
            "pack_weight": 0,
            "bodyweight": 180,
            "distance": 3,
            "duration_s": 3600,
        },
    )
    assert r.status_code == 422  # pack_weight, when given, must be > 0


def test_activity_records_route_input_source(client):
    # A derived-mode log (e.g. GPX import) tags its source; default stays 'manual'.
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Hike",
            "template_key": "hike",
            "pack_weight": 40,
            "bodyweight": 180,
            "distance": 5,
            "source": "gpx",
        },
    )
    assert r.status_code == 201
    assert r.json()["activity"]["source"] == "gpx"
    dflt = client.post(
        "/api/workouts/activity",
        json={"name": "Walk", "template_key": "walk", "distance": 2},
    ).json()
    assert dflt["activity"]["source"] == "manual"


def test_activity_rejects_unknown_route_source(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Hike", "template_key": "hike", "distance": 3, "source": "strava"},
    )
    assert r.status_code == 422  # not in the RouteSource literal


def test_heavier_pack_logs_higher_load(client):
    common = {
        "name": "Hike",
        "template_key": "hike",
        "bodyweight": 180,
        "distance": 5,
        "elevation_gain": 500,
        "duration_s": 4500,
    }
    light = client.post(
        "/api/workouts/activity", json={**common, "pack_weight": 10}
    ).json()["activity"]["metabolic_cost_kj"]
    heavy = client.post(
        "/api/workouts/activity", json={**common, "pack_weight": 50}
    ).json()["activity"]["metabolic_cost_kj"]
    assert heavy > light


# --------------------------------------------------------------------------- #
# Merged athletic-calendar events (formerly a standalone CalendarEvent table,
# merged 2026-07-02 — see alembic merge_calendar_events_into_activity). No
# stored "planned" vs. "happened" status: whether a row is upcoming or
# already occurred is derived purely from started_at/ended_at vs. "now".
# --------------------------------------------------------------------------- #
def test_log_activity_future_date_leaves_ended_at_null(client):
    future = datetime.now(UTC) + timedelta(days=7)
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Mailbox Peak",
            "template_key": "race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": future.isoformat(),
        },
    )
    assert r.status_code == 201
    assert r.json()["ended_at"] is None


def test_log_activity_recurring_weekly_never_closes_out(client):
    # Anchored in the PAST — a plain (non-recurring) past date always closes
    # out immediately, but a recurring series template never does (it's a
    # perpetual series, not a single occurrence).
    past = datetime.now(UTC) - timedelta(days=3)
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "template_key": "league_game",
            "regions": "full",
            "intensity": "hard",
            "started_at": past.isoformat(),
            "recurrence": "weekly",
        },
    )
    assert r.status_code == 201
    ws = r.json()
    assert ws["ended_at"] is None
    assert ws["activity"]["recurrence"] == "weekly"


def test_log_activity_rejects_event_end_date_before_start(client):
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Ski trip",
            "regions": "legs",
            "intensity": "moderate",
            "started_at": "2026-08-10T00:00:00Z",
            "event_end_date": "2026-08-05",
        },
    )
    assert r.status_code == 422


def test_log_activity_rejects_event_end_date_with_weekly_recurrence(client):
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "event_end_date": "2026-08-05",
        },
    )
    assert r.status_code == 422


def test_log_activity_objective_id_must_exist(client):
    r = client.post(
        "/api/workouts/activity",
        json={"name": "Race", "regions": "legs", "intensity": "hard", "objective_id": 999},
    )
    assert r.status_code == 404


def test_log_activity_objective_id_anchors_activity(client):
    obj = client.post(
        "/api/objectives",
        json={"name": "Boston Marathon", "kind": "dated", "target_date": "2026-10-12"},
    ).json()
    r = client.post(
        "/api/workouts/activity",
        json={
            "name": "Boston Marathon",
            "template_key": "race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": "2026-10-12T08:00:00Z",
            "objective_id": obj["id"],
        },
    )
    assert r.status_code == 201
    assert r.json()["activity"]["objective_id"] == obj["id"]


def test_history_list_excludes_future_activities(client):
    future = datetime.now(UTC) + timedelta(days=5)
    client.post(
        "/api/workouts/activity",
        json={
            "name": "Future race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": future.isoformat(),
        },
    )
    client.post(
        "/api/workouts/activity",
        json={
            "name": "Past swim",
            "template_key": "swimming",
            "regions": "full",
            "intensity": "moderate",
        },
    )
    rows = client.get("/api/workouts").json()
    names = {w["name"] for w in rows}
    assert "Past swim" in names
    assert "Future race" not in names


# --------------------------------------------------------------------------- #
# PATCH /workouts/{id} — edit a still-open row, or close one out ("log what
# actually happened") by including ended_at in the same call.
# --------------------------------------------------------------------------- #
def test_patch_activity_updates_estimate_fields(client):
    ws = client.post(
        "/api/workouts/activity",
        json={"name": "Custom", "regions": "full", "intensity": "light"},
    ).json()
    r = client.patch(f"/api/workouts/{ws['id']}", json={"regions": "legs", "intensity": "hard"})
    assert r.status_code == 200
    activity = r.json()["activity"]
    assert activity["regions"] == "legs"
    assert activity["intensity"] == "hard"


def test_patch_activity_sets_ended_at_closes_it_out(client):
    future = datetime.now(UTC) + timedelta(days=2)
    ws = client.post(
        "/api/workouts/activity",
        json={
            "name": "Race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": future.isoformat(),
        },
    ).json()
    assert ws["ended_at"] is None
    now = datetime.now(UTC).isoformat()
    r = client.patch(
        f"/api/workouts/{ws['id']}",
        json={"ended_at": now, "distance": 10, "duration_s": 3000},
    )
    assert r.status_code == 200
    assert r.json()["ended_at"] is not None


def test_patch_activity_rejects_activity_only_fields_on_strength_session(client):
    ws = client.post("/api/workouts", json={}).json()
    r = client.patch(f"/api/workouts/{ws['id']}", json={"regions": "legs"})
    assert r.status_code == 400


def test_patch_materialized_occurrence_rejects_setting_recurrence_weekly(client):
    template = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "started_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    occ_date = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    occurrence = client.post(
        f"/api/workouts/{template['id']}/occurrences", json={"occurrence_date": occ_date}
    ).json()
    r = client.patch(f"/api/workouts/{occurrence['id']}", json={"recurrence": "weekly"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /workouts/{id}/occurrences — materialize a virtual weekly occurrence.
# --------------------------------------------------------------------------- #
def test_materialize_occurrence_creates_linked_session(client):
    template = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "template_key": "league_game",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "started_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    occ_date = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    r = client.post(
        f"/api/workouts/{template['id']}/occurrences", json={"occurrence_date": occ_date}
    )
    assert r.status_code == 201
    occurrence = r.json()
    assert occurrence["recurrence_source_id"] == template["id"]
    assert occurrence["ended_at"] is None
    assert occurrence["activity"]["recurrence"] == "none"
    assert datetime.fromisoformat(occurrence["started_at"]).date().isoformat() == occ_date


def test_materialize_occurrence_is_idempotent(client):
    template = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "started_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    occ_date = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    first = client.post(
        f"/api/workouts/{template['id']}/occurrences", json={"occurrence_date": occ_date}
    ).json()
    second = client.post(
        f"/api/workouts/{template['id']}/occurrences", json={"occurrence_date": occ_date}
    ).json()
    assert first["id"] == second["id"]


def test_materialize_occurrence_404s_on_non_recurring_session(client):
    ws = client.post(
        "/api/workouts/activity",
        json={"name": "One-off", "regions": "full", "intensity": "moderate"},
    ).json()
    r = client.post(
        f"/api/workouts/{ws['id']}/occurrences",
        json={"occurrence_date": datetime.now(UTC).date().isoformat()},
    )
    assert r.status_code == 400
