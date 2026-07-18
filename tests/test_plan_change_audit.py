"""Plan-change audit trail: both loops write events; the program exposes them.
vires-ops#18.
"""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/app/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _spec(template_id: int) -> dict:
    return {
        "name": "8wk",
        "start_date": "2030-01-07",  # far-future Monday
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


def _program(client) -> tuple[dict, int]:
    e = _ex_id(client, "bench press")
    tpl = client.post(
        "/app/api/templates",
        json={"name": "Push", "exercises": [{"exercise_id": e, "target_sets": 3,
              "target_reps": 10, "target_weight": 100}]},
    ).json()
    prog = client.post("/app/api/coach/programs", json={"spec": _spec(tpl["id"])}).json()
    return prog, tpl["id"]


def _changes(client, prog) -> list[dict]:
    return client.get(f"/app/api/coach/programs/{prog['id']}/changes").json()


def test_fresh_program_has_no_changes(client):
    prog, _ = _program(client)
    assert _changes(client, prog) == []


def test_autoregulation_writes_an_audit_event(client):
    prog, _ = _program(client)
    # log week 1 at target -> progress -> autoregulation adjusts upcoming loads
    day1 = prog["planned_workouts"][0]
    ses = client.post(f"/app/api/plan/planned/{day1['id']}/start").json()
    se = ses["exercises"][0]
    for s in se["sets"]:
        client.patch(
            f"/app/api/workouts/{ses['id']}/exercises/{se['id']}/sets/{s['id']}",
            json={"done": True, "reps": 10, "weight": 100},
        )
    client.post(f"/app/api/workouts/{ses['id']}/finish")

    changes = _changes(client, prog)
    assert len(changes) == 1
    ev = changes[0]
    assert ev["source"] == "autoregulation"
    assert ev["session_id"] == ses["id"]
    assert ev["trigger"] == "performance"
    assert ev["detail"]["adjustments"][0]["verdict"] == "progress"


def test_applying_a_revision_writes_an_audit_event(client):
    prog, tpl_id = _program(client)
    # PUT a (re-materialized) spec — the macro apply path; no LLM needed
    r = client.put(f"/app/api/coach/programs/{prog['id']}", json={"spec": _spec(tpl_id)})
    assert r.status_code == 200, r.text

    changes = _changes(client, prog)
    assert len(changes) == 1
    ev = changes[0]
    assert ev["source"] == "plan_revision"
    assert ev["session_id"] is None
    assert ev["detail"]["future_count"] >= 1


def test_changes_404_for_unknown_program(client):
    assert client.get("/app/api/coach/programs/999999/changes").status_code == 404
