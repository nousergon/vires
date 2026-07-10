"""Calendar feed + planned-workout lifecycle (create / start / edit / delete / cascade)."""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta as _timedelta


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


def test_calendar_started_planned_renders_once_not_twice(client):
    # Starting a planned routine creates a linked WorkoutSession. The calendar
    # must emit ONE entry for that workout — the planned row absorbing the
    # session's live status — never a planned "completed" card AND a session
    # "logged" card for the same physical workout (the July-3 duplicate bug).
    tpl = _routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-03", "template_id": tpl["id"]},
    ).json()
    ws = client.post(f"/api/plan/planned/{pw['id']}/start").json()

    cal = client.get(
        "/api/plan/calendar", params={"start": "2020-01-01", "end": "2030-12-31"}
    ).json()
    assert not any(c["kind"] == "session" and c["id"] == ws["id"] for c in cal)
    mine = [c for c in cal if c["kind"] == "planned" and c["id"] == pw["id"]]
    assert len(mine) == 1
    # Session still open ⇒ live status, not pw.status's premature 'completed'.
    assert mine[0]["status"] == "in_progress"
    assert mine[0]["session_id"] == ws["id"]

    client.post(f"/api/workouts/{ws['id']}/finish")
    cal = client.get(
        "/api/plan/calendar", params={"start": "2020-01-01", "end": "2030-12-31"}
    ).json()
    mine = [c for c in cal if c["kind"] == "planned" and c["id"] == pw["id"]]
    assert mine[0]["status"] == "completed"
    assert not any(c["kind"] == "session" and c["id"] == ws["id"] for c in cal)


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


# --------------------------------------------------------------------------- #
# Objectives as calendar events (ICS-feed parity)
# --------------------------------------------------------------------------- #
def _cal(client, start: str, end: str) -> list[dict]:
    return client.get("/api/plan/calendar", params={"start": start, "end": end}).json()


def test_calendar_emits_objective_peak(client):
    o = client.post(
        "/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2026-09-05"},
    ).json()
    cal = _cal(client, "2026-09-01", "2026-09-30")
    peaks = [c for c in cal if c["kind"] == "objective"]
    assert len(peaks) == 1
    assert peaks[0]["status"] == "peak"
    assert peaks[0]["objective_id"] == o["id"]
    assert peaks[0]["date"] == "2026-09-05"


def test_calendar_emits_multi_day_event_window(client):
    client.post(
        "/api/objectives",
        json={
            "name": "Baker trip",
            "kind": "dated",
            "target_date": "2026-09-05",
            "event_end_date": "2026-09-07",
        },
    ).json()
    cal = _cal(client, "2026-09-01", "2026-09-30")
    obj = sorted((c for c in cal if c["kind"] == "objective"), key=lambda c: c["date"])
    # 3 days: peak (9/5) + two event-window days (9/6, 9/7)
    assert [c["date"] for c in obj] == ["2026-09-05", "2026-09-06", "2026-09-07"]
    assert [c["status"] for c in obj] == ["peak", "event", "event"]


def test_calendar_emits_training_block_band(client):
    # Attributed planned workouts (via a coach phase) form the block band.
    e = client.get("/api/exercises/search", params={"q": "bench press"}).json()[0]["exercise"]["id"]
    tpl = client.post(
        "/api/templates",
        json={"name": "Alpine", "exercises": [{"exercise_id": e, "target_sets": 3,
              "target_reps": 5, "target_weight": 100}]},
    ).json()
    o = client.post(
        "/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-07-09", "sport": "alpine"},
    ).json()
    spec = {
        "name": "Season",
        "phases": [
            {"objective_id": o["id"], "start_date": "2030-06-01", "duration_weeks": 3,
             "schedule": [{"template_id": tpl["id"], "weekday": "monday"}]},
        ],
    }
    client.post("/api/coach/programs", json={"spec": spec})

    cal = _cal(client, "2030-06-01", "2030-07-31")
    blocks = [c for c in cal if c["kind"] == "objective_block"]
    assert blocks, "expected a training-block band over the prep span"
    assert all(c["objective_id"] == o["id"] and c["status"] == "block" for c in blocks)
    # the band spans prep → peak (ends at target_date, inclusive — ICS parity), so
    # some block days are strictly before the peak and none fall after it
    assert all(c["date"] <= "2030-07-09" for c in blocks)
    assert any(c["date"] < "2030-07-09" for c in blocks)
    assert any(c["kind"] == "objective" and c["status"] == "peak" for c in cal)


def test_calendar_objective_clipped_to_window(client):
    client.post(
        "/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2026-09-05"},
    ).json()
    # Peak is outside this window -> no objective entries.
    cal = _cal(client, "2026-07-01", "2026-07-31")
    assert not any(c["kind"] in ("objective", "objective_block") for c in cal)


# --------------------------------------------------------------------------- #
# Ailment episodes as calendar bands. `resolved_at` is always stamped as
# real-world "today" by the ailments endpoint (not settable via the API), so
# these anchor onset/window dates relative to `date.today()` rather than
# fixed calendar strings, to stay correct regardless of when the suite runs.
# --------------------------------------------------------------------------- #
def test_calendar_emits_resolved_ailment_band(client):
    onset = _date.today() - _timedelta(days=10)
    ep = client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": onset.isoformat()},
    ).json()
    client.patch(f"/api/ailments/{ep['id']}", json={"status": "resolved"})

    win_start = onset - _timedelta(days=5)
    win_end = _date.today() + _timedelta(days=5)
    cal = _cal(client, win_start.isoformat(), win_end.isoformat())
    band = sorted((c for c in cal if c["kind"] == "ailment"), key=lambda c: c["date"])
    assert band, "expected an ailment band on the calendar"
    assert all(c["id"] == ep["id"] and c["name"] == "Right knee" for c in band)
    # band spans onset -> resolved_at (today), inclusive
    assert band[0]["date"] == onset.isoformat()
    assert band[-1]["date"] == _date.today().isoformat()


def test_calendar_unresolved_ailment_clipped_to_today_not_future(client):
    onset = _date.today() - _timedelta(days=3)
    client.post("/api/ailments", json={"label": "Shoulder", "onset_date": onset.isoformat()})

    win_start = onset - _timedelta(days=2)
    win_end = _date.today() + _timedelta(days=30)
    cal = _cal(client, win_start.isoformat(), win_end.isoformat())
    band = [c["date"] for c in cal if c["kind"] == "ailment"]
    # An unresolved episode's course isn't planned ahead of time — the band
    # stops at today even though the query window extends well past it.
    assert max(band) == _date.today().isoformat()


def test_calendar_ailment_clipped_to_window(client):
    onset = _date.today() - _timedelta(days=5)
    client.post(
        "/api/ailments",
        json={"label": "Old ankle sprain", "onset_date": onset.isoformat()},
    )

    # A window entirely before onset_date doesn't intersect the band at all.
    win_start = onset - _timedelta(days=60)
    win_end = onset - _timedelta(days=20)
    cal = _cal(client, win_start.isoformat(), win_end.isoformat())
    assert not any(c["kind"] == "ailment" for c in cal)


# --------------------------------------------------------------------------- #
# Merged athletic-calendar events on /plan/calendar (formerly a separate
# /calendar-events/window endpoint — merge_calendar_events_into_activity).
# --------------------------------------------------------------------------- #
def test_calendar_feed_virtual_occurrence_and_dedup_against_real_row(client):
    template = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "template_key": "league_game",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "started_at": "2026-08-04T18:00:00Z",
        },
    ).json()
    cal = _cal(client, "2026-08-01", "2026-08-31")
    league = sorted((c for c in cal if c["id"] == template["id"]), key=lambda c: c["date"])
    dates = [c["date"] for c in league]
    assert dates == ["2026-08-04", "2026-08-11", "2026-08-18", "2026-08-25"]
    # the anchor date is the real row (not virtual); every later occurrence
    # in-window is a synthesized, never-persisted projection
    assert [c["virtual"] for c in league] == [False, True, True, True]
    assert all(c["session_type"] == "activity" for c in league)


def test_calendar_feed_materialized_occurrence_stops_being_virtual(client):
    template = client.post(
        "/api/workouts/activity",
        json={
            "name": "Tuesday league",
            "regions": "full",
            "intensity": "hard",
            "recurrence": "weekly",
            "started_at": "2026-08-04T18:00:00Z",
        },
    ).json()
    materialized = client.post(
        f"/api/workouts/{template['id']}/occurrences", json={"occurrence_date": "2026-08-11"}
    ).json()
    cal = _cal(client, "2026-08-01", "2026-08-31")
    ids = (template["id"], materialized["id"])
    league = sorted((c for c in cal if c["id"] in ids), key=lambda c: c["date"])
    by_date = {c["date"]: c for c in league}
    # 8/4 (anchor, real) and 8/11 (now materialized, real) are both non-virtual
    # with distinct ids; 8/18 and 8/25 remain virtual, keyed by the template id.
    assert by_date["2026-08-04"]["virtual"] is False
    assert by_date["2026-08-04"]["id"] == template["id"]
    assert by_date["2026-08-11"]["virtual"] is False
    assert by_date["2026-08-11"]["id"] == materialized["id"]
    assert by_date["2026-08-18"]["virtual"] is True
    assert by_date["2026-08-18"]["id"] == template["id"]
    # exactly one entry per date — no duplicate emission of 8/11
    assert len(league) == 4


def test_calendar_feed_future_activity_status_is_upcoming(client):
    client.post(
        "/api/workouts/activity",
        json={
            "name": "Mailbox Peak",
            "template_key": "race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": "2026-09-12T14:00:00Z",
        },
    )
    cal = _cal(client, "2026-09-01", "2026-09-30")
    race = next(c for c in cal if c["name"] == "Mailbox Peak")
    assert race["status"] == "upcoming"
    assert race["session_type"] == "activity"
    assert race["virtual"] is False


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


def test_start_planned_seeds_dumbbell_weight_per_hand(client):
    ex = _ex_id(client, "dumbbell bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Push",
            "exercises": [{"exercise_id": ex, "target_sets": 2, "target_weight": 90}],
        },
    ).json()
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    assert pw["exercises"][0]["target_weight"] == 90  # prescription stays total

    ses = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    se = ses["exercises"][0]
    assert se["target_weight"] == 45
    assert all(s["weight"] == 45 for s in se["sets"])


def _lower_body_routine(client, name: str = "Legs") -> dict:
    e = _ex_id(client, "squat")
    return client.post(
        "/api/templates",
        json={
            "name": name,
            "exercises": [
                {"exercise_id": e, "target_sets": 3, "target_reps": 5, "target_weight": 100}
            ],
        },
    ).json()


# --------------------------------------------------------------------------- #
# Same-day ailment gate (vires-ops#50) — deterministic, rules-first: warns at
# severity >=5 on a lower-body/knee episode, blocks outright at severity >=8.
# --------------------------------------------------------------------------- #
def test_starting_lower_body_workout_with_knee_severity_seven_surfaces_warning(client):
    tpl = _lower_body_routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 7},
    )

    r = client.post(f"/api/plan/planned/{pw['id']}/start")
    assert r.status_code == 201, r.text
    ses = r.json()
    se = ses["exercises"][0]
    assert se["notes"] is not None
    assert "knee" in se["notes"].lower()
    assert "7/10" in se["notes"]


def test_starting_lower_body_workout_with_knee_severity_eight_is_blocked(client):
    tpl = _lower_body_routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 8},
    )

    r = client.post(f"/api/plan/planned/{pw['id']}/start")
    assert r.status_code == 409
    assert "knee" in r.json()["detail"].lower()
    # never materialized — no session was created.
    assert client.get(f"/api/plan/planned/{pw['id']}").json()["status"] == "planned"


def test_upper_body_exercise_gets_no_warning_note(client):
    # A knee ailment at warn-level severity (7, below the 8 block threshold)
    # flags lower-body exercises but leaves an upper-body prescription's notes
    # untouched — the warning is exercise-scoped, not blanket.
    tpl = _routine(client)  # bench press — not lower-body
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 7},
    )

    r = client.post(f"/api/plan/planned/{pw['id']}/start")
    assert r.status_code == 201, r.text
    assert r.json()["exercises"][0]["notes"] is None


def test_mild_knee_ailment_does_not_warn_or_block(client):
    tpl = _lower_body_routine(client)
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]},
    ).json()
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 3},
    )

    r = client.post(f"/api/plan/planned/{pw['id']}/start")
    assert r.status_code == 201
    assert r.json()["exercises"][0]["notes"] is None


def test_completing_planned_on_a_different_day_moves_marker_to_that_day(client):
    # Doing Thursday's planned workout on Friday should show it on Friday and
    # clear the Thursday marker (the day it actually happened wins). The stored
    # scheduled_date is intentionally left in place — only the calendar marker
    # follows the fulfilling session's date.
    tpl = _routine(client)
    past = "2026-07-01"  # a past scheduled day; starting it completes it "now"
    pw = client.post(
        "/api/plan/planned",
        json={"scheduled_date": past, "template_id": tpl["id"]},
    ).json()
    ses = client.post(f"/api/plan/planned/{pw['id']}/start").json()
    today = ses["started_at"][:10]  # UTC date the session was actually started
    assert today != past  # sanity: the completion day differs from the plan day

    cal = client.get(
        "/api/plan/calendar", params={"start": past, "end": today}
    ).json()
    planned_dates = [e["date"] for e in cal if e["kind"] == "planned"]
    assert past not in planned_dates  # old day no longer marked
    assert today in planned_dates  # planned marker follows to the completion day
    # The fulfilling session is ABSORBED into the planned entry (one workout,
    # one entry) — it must not also appear as its own session card.
    assert not any(e["kind"] == "session" and e["id"] == ses["id"] for e in cal)
    moved = next(e for e in cal if e["kind"] == "planned" and e["id"] == pw["id"])
    assert moved["session_id"] == ses["id"]


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
