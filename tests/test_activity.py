"""Generic cross-training activity quick-log endpoint — Tier 0."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


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
    keys = {t["key"] for t in templates}
    assert "climbing_indoor_toprope" in keys
    for t in templates:
        assert t["regions"] in {"legs", "upper", "full", "core", "none"}
        assert t["intensity"] in {"light", "moderate", "hard"}
