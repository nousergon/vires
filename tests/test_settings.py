"""User settings endpoint tests."""

from __future__ import annotations


def test_settings_defaults_on_first_get(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["weight_unit"] == "lb"
    assert body["default_rest_seconds"] == 90
    assert body["default_sets"] == 3
    assert body["default_reps"] == 8


def test_settings_update_partial(client):
    r = client.put("/api/settings", json={"weight_unit": "kg", "default_rest_seconds": 120})
    assert r.status_code == 200
    body = r.json()
    assert body["weight_unit"] == "kg"
    assert body["default_rest_seconds"] == 120
    assert body["default_sets"] == 3  # untouched

    # persisted
    assert client.get("/api/settings").json()["weight_unit"] == "kg"


def test_settings_validation(client):
    assert client.put("/api/settings", json={"weight_unit": "stone"}).status_code == 422
    assert client.put("/api/settings", json={"default_rest_seconds": -5}).status_code == 422
    assert client.put("/api/settings", json={"default_reps": 0}).status_code == 422


def test_timer_alert_pref_defaults(client):
    body = client.get("/api/settings").json()
    assert body["timer_sound"] is True
    assert body["timer_vibration"] is True
    assert body["timer_notification"] is False  # needs per-device permission
    assert body["timer_keep_awake"] is True


def test_timer_alert_prefs_update(client):
    r = client.put(
        "/api/settings",
        json={"timer_vibration": False, "timer_notification": True, "timer_keep_awake": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["timer_vibration"] is False
    assert body["timer_notification"] is True
    assert body["timer_keep_awake"] is False
    assert body["timer_sound"] is True  # untouched
    # persisted
    assert client.get("/api/settings").json()["timer_notification"] is True


def test_preferred_weekdays_defaults_empty(client):
    assert client.get("/api/settings").json()["preferred_weekdays"] == []


def test_preferred_weekdays_update_and_persist(client):
    r = client.put("/api/settings", json={"preferred_weekdays": ["monday", "thursday"]})
    assert r.status_code == 200
    assert r.json()["preferred_weekdays"] == ["monday", "thursday"]
    # persisted
    assert client.get("/api/settings").json()["preferred_weekdays"] == ["monday", "thursday"]
    # untouched by an unrelated update
    r2 = client.put("/api/settings", json={"weight_unit": "kg"})
    assert r2.json()["preferred_weekdays"] == ["monday", "thursday"]


def test_preferred_weekdays_rejects_invalid_day(client):
    r = client.put("/api/settings", json={"preferred_weekdays": ["someday"]})
    assert r.status_code == 422
