"""Ailment episodes + daily check-ins."""

from __future__ import annotations

from datetime import date, timedelta


def test_create_ailment_with_initial_check_in(client):
    r = client.post(
        "/api/ailments",
        json={
            "label": "Right knee",
            "onset_date": "2026-07-05",
            "notes": "Possible meniscus irritation",
            "initial_severity": 3,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "Right knee"
    assert body["status"] == "active"
    assert body["latest_severity"] == 3
    assert len(body["check_ins"]) == 1


def test_pending_check_ins_excludes_checked_today(client):
    created = client.post(
        "/api/ailments",
        json={"label": "Knee", "initial_severity": 4},
    ).json()
    today = date.today().isoformat()
    pending = client.get("/api/ailments/pending-check-ins", params={"date": today}).json()
    assert pending == []
    # New day with no check-in should appear pending
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    pending2 = client.get("/api/ailments/pending-check-ins", params={"date": tomorrow}).json()
    assert len(pending2) == 1
    assert pending2[0]["ailment"]["id"] == created["id"]


def test_add_check_in_updates_severity(client):
    ep = client.post("/api/ailments", json={"label": "Disc"}).json()
    r = client.post(
        f"/api/ailments/{ep['id']}/check-ins",
        json={"severity": 5, "note": "Walking hurts"},
    )
    assert r.status_code == 201
    assert r.json()["severity"] == 5
    listed = client.get("/api/ailments").json()
    assert listed[0]["latest_severity"] == 5


def test_resolve_ailment(client):
    ep = client.post("/api/ailments", json={"label": "Knee"}).json()
    updated = client.patch(f"/api/ailments/{ep['id']}", json={"status": "resolved"}).json()
    assert updated["status"] == "resolved"
    assert updated["resolved_at"] == date.today().isoformat()
    assert client.get("/api/ailments", params={"status": "open"}).json() == []


def test_check_in_on_resolved_fails(client):
    ep = client.post("/api/ailments", json={"label": "Knee"}).json()
    client.patch(f"/api/ailments/{ep['id']}", json={"status": "resolved"})
    r = client.post(f"/api/ailments/{ep['id']}/check-ins", json={"severity": 1})
    assert r.status_code == 400
