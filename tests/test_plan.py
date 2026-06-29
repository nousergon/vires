"""Calendar feed + planned-workout lifecycle (create / start / edit / delete / cascade)."""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _routine(client, name: str = "R") -> dict:
    e1 = _ex_id(client, "bench press")
    return client.post(
        "/api/templates",
        json={
            "name": name,
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 5, "target_weight": 100}
            ],
        },
    ).json()


def test_create_planned_from_template(client):
    tpl = _routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    assert pw["status"] == "planned"
    assert pw["created_by"] == "user"
    assert pw["name"] == "R"
    assert pw["exercises"][0]["target_weight"] == 100


def test_calendar_merges_past_session_and_future_planned(client):
    # A completed session "today" + a planned workout in the future.
    ws = client.post("/api/workouts", json={"name": "Today"}).json()
    client.post(f"/api/workouts/{ws['id']}/finish")
    pw = client.post("/api/plan/planned", json={"scheduled_date": "2030-01-01"}).json()

    cal = client.get(
        "/api/plan/calendar", params={"start": "2020-01-01", "end": "2030-12-31"}
    ).json()
    sessions = [c for c in cal if c["kind"] == "session"]
    planned = [c for c in cal if c["kind"] == "planned"]
    assert any(c["id"] == ws["id"] and c["status"] == "completed" for c in sessions)
    assert any(c["id"] == pw["id"] and c["status"] == "planned" for c in planned)


def test_calendar_respects_range(client):
    client.post("/api/plan/planned", json={"scheduled_date": "2026-07-15"}).json()
    inside = client.get(
        "/api/plan/calendar", params={"start": "2026-07-01", "end": "2026-07-31"}
    ).json()
    outside = client.get(
        "/api/plan/calendar", params={"start": "2026-08-01", "end": "2026-08-31"}
    ).json()
    assert any(c["kind"] == "planned" for c in inside)
    assert not any(c["kind"] == "planned" for c in outside)


def test_calendar_rejects_inverted_range(client):
    r = client.get("/api/plan/calendar", params={"start": "2026-08-01", "end": "2026-07-01"})
    assert r.status_code == 400


def test_start_planned_seeds_session_from_prescription_and_links(client):
    tpl = _routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    ses = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    assert ses["template_id"] == tpl["id"]
    se = ses["exercises"][0]
    # Sets seeded straight from the prescription (3x5 @ 100), NOT last-performance.
    assert len(se["sets"]) == 3
    assert all(s["reps"] == 5 and s["weight"] == 100 for s in se["sets"])

    got = client.get(f"/api/plan/planned/{pw['id']}").json()
    assert got["status"] == "completed"
    assert got["session_id"] == ses["id"]


def test_delete_session_started_from_plan_detaches_and_reverts(client):
    # Regression: deleting a session that fulfilled a planned workout used to hit
    # the planned_workouts.session_id FK (500) and silently fail in the UI.
    tpl = _routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    ses = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    assert client.get(f"/api/plan/planned/{pw['id']}").json()["status"] == "completed"

    # delete the logged session — must succeed, not 500
    assert client.delete(f"/api/workouts/{ses['id']}").status_code == 204

    # the planned day is detached + reverted to 'planned' (its log is gone)
    got = client.get(f"/api/plan/planned/{pw['id']}").json()
    assert got["status"] == "planned"
    assert got["session_id"] is None
    # the session is actually gone
    assert client.get(f"/api/workouts/{ses['id']}").status_code == 404


def test_start_planned_is_idempotent(client):
    tpl = _routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    first = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    again = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    assert again["id"] == first["id"]  # no duplicate session


def test_patch_planned_reschedule_and_status(client):
    pw = client.post("/api/plan/planned", json={"scheduled_date": "2026-07-01"}).json()
    upd = client.patch(
        f"/api/plan/planned/{pw['id']}",
        json={"scheduled_date": "2026-07-08", "status": "skipped", "name": "Moved"},
    ).json()
    assert upd["scheduled_date"] == "2026-07-08"
    assert upd["status"] == "skipped"
    assert upd["name"] == "Moved"


def test_patch_planned_rejects_bad_status(client):
    pw = client.post("/api/plan/planned", json={"scheduled_date": "2026-07-01"}).json()
    r = client.patch(f"/api/plan/planned/{pw['id']}", json={"status": "nonsense"})
    assert r.status_code == 400


def test_delete_planned(client):
    pw = client.post("/api/plan/planned", json={"scheduled_date": "2026-07-01"}).json()
    assert client.delete(f"/api/plan/planned/{pw['id']}").status_code == 204
    assert client.get(f"/api/plan/planned/{pw['id']}").status_code == 404


def test_planned_404(client):
    assert client.get("/api/plan/planned/99999999").status_code == 404


def _program_spec(template_id: int, weeks: int = 8) -> dict:
    return {
        "name": "8wk",
        "start_date": "2026-06-29",  # Monday
        "duration_weeks": weeks,
        "schedule": [{"template_id": template_id, "weekday": 0}],
        "progressions": [
            {
                "template_id": template_id,
                "reps": {"mode": "linear", "start": 10, "end": 4},
                "weight": {"mode": "percent_of_start", "start": 1.0, "end": 1.3},
            }
        ],
        "deload_weeks": [4],
        "coach_summary": "ramp",
    }


def test_program_save_lists_and_cascade_deletes(client):
    tpl = _routine(client, "Upper")
    prog = client.post("/api/coach/programs", json={"spec": _program_spec(tpl["id"])}).json()
    assert len(prog["planned_workouts"]) == 8

    progs = client.get("/api/plan/programs").json()
    summary = next(p for p in progs if p["id"] == prog["id"])
    assert summary["planned_count"] == 8
    assert summary["completed_count"] == 0

    # all 8 land on the calendar tagged with the program id
    cal = client.get(
        "/api/plan/calendar", params={"start": "2026-06-01", "end": "2026-09-30"}
    ).json()
    program_days = [c for c in cal if c["kind"] == "planned" and c["program_id"] == prog["id"]]
    assert len(program_days) == 8

    # cascade delete removes the planned workouts too
    assert client.delete(f"/api/plan/programs/{prog['id']}").status_code == 204
    cal2 = client.get(
        "/api/plan/calendar", params={"start": "2026-06-01", "end": "2026-09-30"}
    ).json()
    assert not any(c["kind"] == "planned" and c.get("program_id") == prog["id"] for c in cal2)


def test_program_completed_count_tracks_started(client):
    tpl = _routine(client, "Upper")
    prog = client.post(
        "/api/coach/programs", json={"spec": _program_spec(tpl["id"], weeks=2)}
    ).json()
    first_day = prog["planned_workouts"][0]["id"]
    client.post(f"/api/plan/planned/{first_day}/start")
    summary = next(p for p in client.get("/api/plan/programs").json() if p["id"] == prog["id"])
    assert summary["completed_count"] == 1


def test_calendar_entries_carry_objective_label(client):
    alpine = _routine(client, "Alpine")
    o = client.post(
        "/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-07-09", "sport": "alpine"},
    ).json()
    spec = {
        "name": "Season",
        "phases": [
            {"objective_id": o["id"], "start_date": "2030-06-01", "duration_weeks": 2,
             "schedule": [{"template_id": alpine["id"], "weekday": "monday"}]},
        ],
    }
    client.post("/api/coach/programs", json={"spec": spec})
    cal = client.get(
        "/api/plan/calendar", params={"start": "2030-01-01", "end": "2030-12-31"}
    ).json()
    attributed = [c for c in cal if c["kind"] == "planned" and c["objective_id"] == o["id"]]
    assert attributed and all(c["objective_name"] == "Baker" for c in attributed)


def test_save_phased_season_attributes_workouts_and_skips_event(client):
    """A two-objective season: each phase's workouts carry its objective_id, and
    no training is scheduled across Baker's multi-day event."""
    alpine = _routine(client, "Alpine")
    rock = _routine(client, "Rock")
    baker = client.post(
        "/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-06-23",
              "event_end_date": "2030-06-25", "sport": "alpine"},
    ).json()
    kt = client.post(
        "/api/objectives",
        json={"name": "Kangaroo Temple", "kind": "dated", "target_date": "2030-07-21"},
    ).json()
    spec = {
        "name": "Cascades season",
        "phases": [
            {"objective_id": baker["id"], "name": "Baker block",
             "start_date": "2030-06-03", "duration_weeks": 3,
             "schedule": [{"template_id": alpine["id"], "weekday": "monday"}]},
            {"objective_id": kt["id"], "name": "Kangaroo Temple block",
             "start_date": "2030-06-29", "duration_weeks": 3,
             "schedule": [{"template_id": rock["id"], "weekday": "monday"}]},
        ],
    }
    prog = client.post("/api/coach/programs", json={"spec": spec}).json()
    days = prog["planned_workouts"]
    # every workout is attributed to its block's objective
    for d in days:
        expected = baker["id"] if d["template_id"] == alpine["id"] else kt["id"]
        assert d["objective_id"] == expected
    # no training during Baker's event (6/23–6/25)
    assert not any("2030-06-23" <= d["scheduled_date"] <= "2030-06-25" for d in days)
    # both blocks materialized (3 weeks each)
    assert sum(1 for d in days if d["objective_id"] == baker["id"]) == 3
    assert sum(1 for d in days if d["objective_id"] == kt["id"]) == 3
