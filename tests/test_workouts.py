"""Workout logging: start (empty/from-template), log sets, finish, history, prev-perf."""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def test_empty_workout_log_and_finish(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/workouts", json={"name": "Quick"}).json()
    assert ws["template_id"] is None and ws["exercises"] == []

    se = client.post(f"/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s1 = client.post(
        f"/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 225},
    ).json()
    assert s1["set_number"] == 1
    s2 = client.post(
        f"/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 235},
    ).json()
    assert s2["set_number"] == 2

    fin = client.post(f"/workouts/{ws['id']}/finish").json()
    assert fin["ended_at"] is not None
    assert len(fin["exercises"][0]["sets"]) == 2


def test_start_from_template_clones_exercises(client):
    e1, e2 = _ex_id(client, "bench press"), _ex_id(client, "squat")
    tpl = client.post(
        "/templates",
        json={
            "name": "Full Body",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 5, "rest_seconds": 120},
                {"exercise_id": e2, "target_sets": 3, "target_reps": 8},
            ],
        },
    ).json()
    ws = client.post("/workouts", json={"template_id": tpl["id"]}).json()
    assert ws["name"] == "Full Body"
    assert ws["template_id"] == tpl["id"]
    assert [se["exercise"]["id"] for se in ws["exercises"]] == [e1, e2]
    assert ws["exercises"][0]["target_sets"] == 3
    assert ws["exercises"][0]["rest_seconds"] == 120


def test_previous_performance_hint(client):
    ex = _ex_id(client, "barbell curl")
    # First session: log 3x10@50, finish.
    w1 = client.post("/workouts", json={"name": "Day 1"}).json()
    se1 = client.post(f"/workouts/{w1['id']}/exercises", json={"exercise_id": ex}).json()
    for _ in range(3):
        client.post(
            f"/workouts/{w1['id']}/exercises/{se1['id']}/sets",
            json={"reps": 10, "weight": 50},
        )
    client.post(f"/workouts/{w1['id']}/finish")

    # Second session: adding the same exercise surfaces last time's sets.
    w2 = client.post("/workouts", json={"name": "Day 2"}).json()
    se2 = client.post(f"/workouts/{w2['id']}/exercises", json={"exercise_id": ex}).json()
    prev = se2["previous_performance"]
    assert prev is not None
    assert prev["session_id"] == w1["id"]
    assert len(prev["sets"]) == 3
    assert prev["sets"][0]["weight"] == 50


def test_history_list_and_volume(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/workouts", json={"name": "Vol"}).json()
    se = client.post(f"/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    client.post(f"/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100})
    client.post(
        f"/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 10, "weight": 0, "is_warmup": True},
    )
    rows = client.get("/workouts").json()
    row = next(r for r in rows if r["id"] == ws["id"])
    assert row["set_count"] == 2
    assert row["total_volume"] == 500.0  # warmup + zero-weight excluded


def test_update_and_delete_set(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/workouts", json={}).json()
    se = client.post(f"/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s = client.post(
        f"/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    ).json()

    upd = client.patch(
        f"/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}", json={"weight": 110}
    ).json()
    assert upd["weight"] == 110 and upd["reps"] == 5

    delr = client.delete(f"/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}")
    assert delr.status_code == 204
    got = client.get(f"/workouts/{ws['id']}").json()
    assert got["exercises"][0]["sets"] == []


def test_workout_404(client):
    assert client.get("/workouts/99999999").status_code == 404
