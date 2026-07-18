"""Personal records: per-exercise bests + time-window filtering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _ex_id(client, q: str) -> int:
    return client.get("/app/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _log_session(client, q: str, sets: list[tuple[float, int]], *, name: str = "W"):
    """Start a workout, log performed (weight, reps) sets for an exercise, finish."""
    ex = _ex_id(client, q)
    ws = client.post("/app/api/workouts", json={"name": name}).json()
    se = client.post(f"/app/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    for weight, reps in sets:
        client.post(
            f"/app/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
            json={"reps": reps, "weight": weight},
        )
    client.post(f"/app/api/workouts/{ws['id']}/finish")
    return ws, ex


def _record_for(records: list[dict], exercise_id: int) -> dict | None:
    return next((r for r in records if r["exercise"]["id"] == exercise_id), None)


def test_records_compute_all_metrics(client):
    _, ex = _log_session(client, "bench press", [(135, 10), (185, 5), (225, 3)])
    recs = client.get("/app/api/records", params={"window": "all"}).json()
    r = _record_for(recs, ex)
    assert r is not None
    assert r["heaviest"]["value"] == 225
    assert r["best_set_volume"]["value"] == 1350  # 135 * 10
    assert r["most_reps"]["value"] == 10
    # Epley: max(135*1.333, 185*1.1667, 225*1.1) = 225*1.1 = 247.5
    assert r["est_1rm"]["value"] == 247.5
    assert r["est_1rm"]["weight"] == 225 and r["est_1rm"]["reps"] == 3


def test_records_exclude_warmup(client):
    ex = _ex_id(client, "bench press")
    ws = client.post("/app/api/workouts", json={}).json()
    se = client.post(f"/app/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    sets_url = f"/app/api/workouts/{ws['id']}/exercises/{se['id']}/sets"
    client.post(sets_url, json={"reps": 5, "weight": 100})
    client.post(sets_url, json={"reps": 1, "weight": 315, "is_warmup": True})  # warmup ≠ PR
    r = _record_for(client.get("/app/api/records").json(), ex)
    assert r["heaviest"]["value"] == 100


def test_records_exclude_unperformed_planned_sets(client):
    # A planned workout's seeded sets have completed_at=None → must not count.
    tpl = client.post(
        "/app/api/templates",
        json={
            "name": "R",
            "exercises": [
                {
                    "exercise_id": _ex_id(client, "bench press"),
                    "target_sets": 3,
                    "target_reps": 5,
                    "target_weight": 999,
                }
            ],
        },
    ).json()
    pw = client.post(
        "/app/api/plan/planned", json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]}
    ).json()
    client.post(f"/app/api/plan/planned/{pw['id']}/start")  # seeds sets, none completed
    recs = client.get("/app/api/records").json()
    # No performed set exists → the 999 lb seeded target must not appear as a PR.
    assert all(
        (r["heaviest"] is None or r["heaviest"]["value"] != 999) for r in recs
    )


def test_records_timed_longest_hold(client):
    hits = client.get("/app/api/exercises/search", params={"q": "plank"}).json()
    plank = next(h["exercise"] for h in hits if h["exercise"]["name"].lower() == "plank")
    ws = client.post("/app/api/workouts", json={}).json()
    se = client.post(
        f"/app/api/workouts/{ws['id']}/exercises", json={"exercise_id": plank["id"]}
    ).json()
    for d in (30, 60, 45):
        client.post(
            f"/app/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"duration_seconds": d}
        )
    r = _record_for(client.get("/app/api/records").json(), plank["id"])
    assert r is not None and r["is_timed"] is True
    assert r["longest_hold"]["value"] == 60
    assert r["est_1rm"] is None and r["heaviest"] is None


def test_records_window_filters_by_session_date(client, db):
    from api.db.models import WorkoutSession

    ws, ex = _log_session(client, "barbell deadlift", [(315, 5)])
    # Backdate the session ~200 days so it falls outside month/quarter but inside year.
    session = db.get(WorkoutSession, ws["id"])
    session.started_at = datetime.now(UTC) - timedelta(days=200)
    db.commit()

    month = client.get("/app/api/records", params={"window": "month"}).json()
    quarter = client.get("/app/api/records", params={"window": "quarter"}).json()
    year = client.get("/app/api/records", params={"window": "year"}).json()
    all_time = client.get("/app/api/records", params={"window": "all"}).json()
    assert _record_for(month, ex) is None
    assert _record_for(quarter, ex) is None
    assert _record_for(year, ex) is not None
    assert _record_for(all_time, ex) is not None


def test_records_invalid_window_rejected(client):
    assert client.get("/app/api/records", params={"window": "decade"}).status_code == 422


def test_records_empty_when_no_history(client):
    assert client.get("/app/api/records").json() == []
