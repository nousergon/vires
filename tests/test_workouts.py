"""Workout logging: start (empty/from-template), log sets, finish, history, prev-perf."""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def test_empty_workout_log_and_finish(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={"name": "Quick"}).json()
    assert ws["template_id"] is None and ws["exercises"] == []

    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s1 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 225},
    ).json()
    assert s1["set_number"] == 1
    s2 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 235},
    ).json()
    assert s2["set_number"] == 2

    fin = client.post(f"/api/workouts/{ws['id']}/finish").json()
    assert fin["ended_at"] is not None
    assert len(fin["exercises"][0]["sets"]) == 2


def test_start_from_template_clones_exercises(client):
    e1, e2 = _ex_id(client, "bench press"), _ex_id(client, "squat")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Full Body",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 5, "rest_seconds": 120},
                {"exercise_id": e2, "target_sets": 3, "target_reps": 8},
            ],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    assert ws["name"] == "Full Body"
    assert ws["template_id"] == tpl["id"]
    assert [se["exercise"]["id"] for se in ws["exercises"]] == [e1, e2]
    assert ws["exercises"][0]["target_sets"] == 3
    assert ws["exercises"][0]["rest_seconds"] == 120


def test_start_from_template_seeds_planned_sets(client):
    e1 = _ex_id(client, "bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Seeded",
            "exercises": [{"exercise_id": e1, "target_sets": 3, "target_reps": 8}],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert len(se["sets"]) == 3  # planned rows pre-created
    assert se["sets"][0]["reps"] == 8  # prefilled from target reps
    assert se["sets"][0]["completed_at"] is None  # not done yet


def test_template_target_weight_seeds_set_weight(client):
    e1 = _ex_id(client, "bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Weighted",
            "exercises": [
                {"exercise_id": e1, "target_sets": 2, "target_reps": 5, "target_weight": 135}
            ],
        },
    ).json()
    assert tpl["exercises"][0]["target_weight"] == 135
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert se["target_weight"] == 135
    assert all(s["weight"] == 135 for s in se["sets"])  # planned sets seeded with it


def test_target_weight_used_despite_blank_prior_history(client):
    e1 = _ex_id(client, "bench press")
    # Prior session where the exercise was logged with NO weight (e.g. an
    # earlier planned set left blank) — must not suppress the routine's weight.
    w0 = client.post("/api/workouts", json={}).json()
    se0 = client.post(f"/api/workouts/{w0['id']}/exercises", json={"exercise_id": e1}).json()
    client.post(f"/api/workouts/{w0['id']}/exercises/{se0['id']}/sets", json={"reps": 5})
    client.post(f"/api/workouts/{w0['id']}/finish")

    tpl = client.post(
        "/api/templates",
        json={
            "name": "W",
            "exercises": [{"exercise_id": e1, "target_sets": 1, "target_weight": 135}],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    assert ws["exercises"][0]["sets"][0]["weight"] == 135


def test_timed_exercise_seeds_duration_and_flags(client):
    hits = client.get("/api/exercises/search", params={"q": "plank"}).json()
    plank = next(h["exercise"] for h in hits if h["exercise"]["name"].lower() == "plank")
    assert plank["is_timed"] is True
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Core",
            "exercises": [
                {"exercise_id": plank["id"], "target_sets": 2, "target_duration_seconds": 60}
            ],
        },
    ).json()
    assert tpl["exercises"][0]["target_duration_seconds"] == 60
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert se["exercise"]["is_timed"] is True
    assert se["target_duration_seconds"] == 60
    assert [s["duration_seconds"] for s in se["sets"]] == [60, 60]
    assert all(s["reps"] is None for s in se["sets"])  # timed: no reps


def test_mark_set_done_toggles_completed_at(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    ).json()

    done = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}",
        json={"done": True, "weight": 105},
    ).json()
    assert done["completed_at"] is not None
    assert done["weight"] == 105

    undone = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}", json={"done": False}
    ).json()
    assert undone["completed_at"] is None


def test_started_at_is_timezone_aware(client):
    ws = client.post("/api/workouts", json={}).json()
    # tz-aware ISO so clients don't misread UTC as local (elapsed-timer fix)
    assert ws["started_at"].endswith("+00:00") or ws["started_at"].endswith("Z")


def test_previous_performance_hint(client):
    ex = _ex_id(client, "barbell curl")
    # First session: log 3x10@50, finish.
    w1 = client.post("/api/workouts", json={"name": "Day 1"}).json()
    se1 = client.post(f"/api/workouts/{w1['id']}/exercises", json={"exercise_id": ex}).json()
    for _ in range(3):
        client.post(
            f"/api/workouts/{w1['id']}/exercises/{se1['id']}/sets",
            json={"reps": 10, "weight": 50},
        )
    client.post(f"/api/workouts/{w1['id']}/finish")

    # Second session: adding the same exercise surfaces last time's sets.
    w2 = client.post("/api/workouts", json={"name": "Day 2"}).json()
    se2 = client.post(f"/api/workouts/{w2['id']}/exercises", json={"exercise_id": ex}).json()
    prev = se2["previous_performance"]
    assert prev is not None
    assert prev["session_id"] == w1["id"]
    assert len(prev["sets"]) == 3
    assert prev["sets"][0]["weight"] == 50


def test_history_list_and_volume(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={"name": "Vol"}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    )
    client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 10, "weight": 0, "is_warmup": True},
    )
    rows = client.get("/api/workouts").json()
    row = next(r for r in rows if r["id"] == ws["id"])
    assert row["set_count"] == 2
    assert row["total_volume"] == 500.0  # warmup + zero-weight excluded


def test_update_and_delete_set(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    ).json()

    upd = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}", json={"weight": 110}
    ).json()
    assert upd["weight"] == 110 and upd["reps"] == 5

    delr = client.delete(f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}")
    assert delr.status_code == 204
    got = client.get(f"/api/workouts/{ws['id']}").json()
    assert got["exercises"][0]["sets"] == []


def test_workout_404(client):
    assert client.get("/api/workouts/99999999").status_code == 404
