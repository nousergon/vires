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
