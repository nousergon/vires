"""End-to-end autoregulation: finishing a planned session adjusts the next
planned occurrences of each exercise (deterministic micro loop, vires-ops#17).

Program dates are far-future so "upcoming" holds regardless of test run date.
"""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _push_template(client) -> dict:
    e = _ex_id(client, "bench press")
    return client.post(
        "/api/templates",
        json={
            "name": "Push",
            "exercises": [
                {"exercise_id": e, "target_sets": 3, "target_reps": 10, "target_weight": 100}
            ],
        },
    ).json()


def _spec(template_id: int) -> dict:
    return {
        "name": "8wk",
        "start_date": "2030-01-07",  # a Monday, far enough out to stay "upcoming"
        "duration_weeks": 8,
        "schedule": [{"template_id": template_id, "weekday": "monday"}],
        "progressions": [
            {
                "template_id": template_id,
                "reps": {"mode": "linear", "start": 10, "end": 4},
                "weight": {"mode": "percent_of_start", "start": 1.0, "end": 1.3},
            }
        ],
        "deload_weeks": [],
        "coach_summary": "ramp",
    }


def _program(client) -> dict:
    tpl = _push_template(client)
    return client.post("/api/coach/programs", json={"spec": _spec(tpl["id"])}).json()


def _log_week1(client, prog, *, reps: int, weight: float) -> None:
    """Start week 1, log all its sets at the given reps/weight, finish."""
    day1 = prog["planned_workouts"][0]
    ses = client.post(f"/api/plan/planned/{day1['id']}/start").json()
    se = ses["exercises"][0]
    for s in se["sets"]:
        client.patch(
            f"/api/workouts/{ses['id']}/exercises/{se['id']}/sets/{s['id']}",
            json={"done": True, "reps": reps, "weight": weight},
        )
    client.post(f"/api/workouts/{ses['id']}/finish")


def _week2_weight(client, prog) -> float:
    pid = prog["planned_workouts"][1]["id"]
    return client.get(f"/api/plan/planned/{pid}").json()["exercises"][0]["target_weight"]


def test_beating_targets_bumps_next_planned_loads(client):
    prog = _program(client)
    before = _week2_weight(client, prog)
    _log_week1(client, prog, reps=10, weight=100)  # hit 3x10 @ 100 -> progress
    assert _week2_weight(client, prog) == before + 2.5


def test_missing_targets_backs_off_next_planned_loads(client):
    prog = _program(client)
    before = _week2_weight(client, prog)
    _log_week1(client, prog, reps=8, weight=100)  # 2 reps short at weight -> back_off
    assert _week2_weight(client, prog) == before - 2.5


def test_kill_switch_disables_autoregulation(client, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "autoregulation_enabled", False)
    prog = _program(client)
    before = _week2_weight(client, prog)
    _log_week1(client, prog, reps=10, weight=100)
    assert _week2_weight(client, prog) == before  # unchanged


def test_adhoc_session_finish_is_a_noop(client):
    # A plain session (no plan link) must finish cleanly — autoregulation no-ops.
    ws = client.post("/api/workouts", json={"name": "Ad hoc"}).json()
    r = client.post(f"/api/workouts/{ws['id']}/finish")
    assert r.status_code == 200 and r.json()["ended_at"] is not None
