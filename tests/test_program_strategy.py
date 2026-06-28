"""A saved plan links to the active objective + surfaces the coach's strategy."""

from __future__ import annotations


def _template(client) -> int:
    ex = client.get("/api/exercises/search", params={"q": "bench press"}).json()[0]
    return client.post(
        "/api/templates",
        json={
            "name": "Upper",
            "exercises": [
                {"exercise_id": ex["exercise"]["id"], "target_sets": 3, "target_reps": 5}
            ],
        },
    ).json()["id"]


def _spec(template_id: int) -> dict:
    return {
        "name": "Block",
        "start_date": "2026-06-29",
        "duration_weeks": 4,
        "new_routines": [],
        "schedule": [{"template_id": template_id, "weekday": "monday"}],
        "progressions": [],
        "deload_weeks": [],
        "coach_summary": "Base, then peak strength, then taper to the summit.",
    }


def _set_objective(client):
    client.post(
        "/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2026-09-05",
              "sport": "alpine", "is_primary": True},
    )


def test_saved_program_links_objective_and_exposes_summary(client):
    _set_objective(client)
    tid = _template(client)
    prog = client.post("/api/coach/programs", json={"spec": _spec(tid)}).json()
    summary = "Base, then peak strength, then taper to the summit."

    # the saved program carries the strategy + the objective link
    assert prog["coach_summary"] == summary
    assert prog["objective_id"] is not None

    # /plan/programs surfaces both
    summ = client.get("/api/plan/programs").json()[0]
    assert summ["coach_summary"] == summary
    assert summ["objective_id"] == prog["objective_id"]

    # /objectives/active surfaces the active plan's strategy (for the tile)
    active = client.get("/api/objectives/active").json()
    assert active["active_program"]["program_id"] == prog["id"]
    assert active["active_program"]["coach_summary"] == summary


def test_program_without_objective_has_null_link(client):
    tid = _template(client)
    prog = client.post("/api/coach/programs", json={"spec": _spec(tid)}).json()
    assert prog["objective_id"] is None
    active = client.get("/api/objectives/active").json()
    assert active["active_program"] is None  # no objective set


def test_deleting_objective_nulls_program_link_but_keeps_plan(client):
    _set_objective(client)
    tid = _template(client)
    prog = client.post("/api/coach/programs", json={"spec": _spec(tid)}).json()
    oid = prog["objective_id"]

    assert client.delete(f"/api/objectives/{oid}").status_code == 204

    # the plan survives; only the link is nulled (ON DELETE SET NULL)
    summ = client.get("/api/plan/programs").json()
    row = next(p for p in summ if p["id"] == prog["id"])
    assert row["objective_id"] is None
    assert row["coach_summary"]  # strategy still readable from the spec
