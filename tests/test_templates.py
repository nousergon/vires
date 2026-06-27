"""Workout template (Routine) CRUD tests."""

from __future__ import annotations


def _two_exercise_ids(client) -> list[int]:
    a = client.get("/api/exercises/search", params={"q": "bench press"}).json()
    b = client.get("/api/exercises/search", params={"q": "squat"}).json()
    return [a[0]["exercise"]["id"], b[0]["exercise"]["id"]]


def test_create_and_get_template(client):
    e1, e2 = _two_exercise_ids(client)
    r = client.post(
        "/api/templates",
        json={
            "name": "Push Day",
            "notes": "heavy",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 5, "rest_seconds": 180},
                {"exercise_id": e2, "target_sets": 5, "target_reps": 5},
            ],
        },
    )
    assert r.status_code == 201
    tpl = r.json()
    assert tpl["name"] == "Push Day"
    assert [te["order_index"] for te in tpl["exercises"]] == [0, 1]
    assert tpl["exercises"][0]["target_sets"] == 3

    got = client.get(f"/api/templates/{tpl['id']}")
    assert got.status_code == 200
    assert got.json()["exercises"][1]["exercise"]["id"] == e2


def test_list_templates(client):
    e1, _ = _two_exercise_ids(client)
    client.post("/api/templates", json={"name": "A", "exercises": [{"exercise_id": e1}]})
    client.post("/api/templates", json={"name": "B", "exercises": []})
    rows = client.get("/api/templates").json()
    names = {t["name"] for t in rows}
    assert {"A", "B"} <= names
    a = next(t for t in rows if t["name"] == "A")
    assert a["exercise_count"] == 1


def test_update_template_replaces_exercises(client):
    e1, e2 = _two_exercise_ids(client)
    tpl = client.post(
        "/api/templates", json={"name": "Leg Day", "exercises": [{"exercise_id": e1}]}
    ).json()
    r = client.put(
        f"/api/templates/{tpl['id']}",
        json={"name": "Leg Day v2", "exercises": [{"exercise_id": e2, "target_sets": 4}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Leg Day v2"
    assert len(body["exercises"]) == 1
    assert body["exercises"][0]["exercise"]["id"] == e2


def test_delete_template(client):
    tpl = client.post("/api/templates", json={"name": "Temp", "exercises": []}).json()
    assert client.delete(f"/api/templates/{tpl['id']}").status_code == 204
    assert client.get(f"/api/templates/{tpl['id']}").status_code == 404


def test_create_template_unknown_exercise_400(client):
    r = client.post(
        "/api/templates", json={"name": "Bad", "exercises": [{"exercise_id": 99999999}]}
    )
    assert r.status_code == 400
