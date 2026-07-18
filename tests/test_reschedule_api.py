"""End-to-end coverage of POST /plan/reschedule-missed, through the real
router/service/DB stack (not just the pure placement logic — see
tests/test_reschedule.py for that).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

TODAY = date.today()


def _one_off(client, scheduled_date: date, name: str = "Lift") -> dict:
    return client.post(
        "/app/api/plan/planned", json={"scheduled_date": scheduled_date.isoformat(), "name": name}
    ).json()


def _hard_event(client, event_date: date, event_end_date: date | None = None) -> dict:
    return client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Mailbox Peak",
            "template_key": "recreation_event",
            "regions": "legs",
            "intensity": "hard",
            "duration_s": 21600,
            "started_at": datetime.combine(event_date, datetime.min.time()).isoformat(),
            "event_end_date": event_end_date.isoformat() if event_end_date else None,
        },
    ).json()


def test_reschedule_moves_missed_workout_to_today(client):
    pw = _one_off(client, TODAY - timedelta(days=1), name="Upper Body")
    r = client.post("/app/api/plan/reschedule-missed")
    assert r.status_code == 200
    moved = r.json()
    assert len(moved) == 1
    assert moved[0]["id"] == pw["id"]
    assert moved[0]["scheduled_date"] == TODAY.isoformat()
    assert moved[0]["rescheduled_from"] == (TODAY - timedelta(days=1)).isoformat()

    # Also visible on the calendar feed with provenance intact.
    cal = client.get(
        "/app/api/plan/calendar",
        params={"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=1)).isoformat()},
    ).json()
    entry = next(e for e in cal if e["kind"] == "planned" and e["id"] == pw["id"])
    assert entry["date"] == TODAY.isoformat()
    assert entry["rescheduled_from"] == (TODAY - timedelta(days=1)).isoformat()


def test_reschedule_respects_existing_occupant(client):
    _one_off(client, TODAY)  # today is already spoken for
    missed = _one_off(client, TODAY - timedelta(days=1))
    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert len(moved) == 1
    assert moved[0]["id"] == missed["id"]
    assert moved[0]["scheduled_date"] == (TODAY + timedelta(days=1)).isoformat()


def test_reschedule_leaves_untouched_when_horizon_is_fully_occupied(client):
    for i in range(14):  # today .. today+13 (the flat DEFAULT_HORIZON_DAYS)
        _one_off(client, TODAY + timedelta(days=i))
    missed = _one_off(client, TODAY - timedelta(days=1))

    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert moved == []

    still = client.get(f"/app/api/plan/planned/{missed['id']}").json()
    assert still["scheduled_date"] == (TODAY - timedelta(days=1)).isoformat()
    assert still["status"] == "planned"


def test_reschedule_ignores_skipped_workouts(client):
    pw = _one_off(client, TODAY - timedelta(days=1))
    client.patch(f"/app/api/plan/planned/{pw['id']}", json={"status": "skipped"})
    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert moved == []


def test_reschedule_ignores_already_started_workouts(client):
    pw = _one_off(client, TODAY - timedelta(days=1))
    client.post(f"/app/api/plan/planned/{pw['id']}/start")  # flips status -> completed
    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert moved == []


def test_reschedule_is_idempotent_on_repeat_call(client):
    _one_off(client, TODAY - timedelta(days=1))
    first = client.post("/app/api/plan/reschedule-missed").json()
    assert len(first) == 1
    second = client.post("/app/api/plan/reschedule-missed").json()
    assert second == []


def test_reschedule_avoids_collision_across_two_missed_workouts(client):
    older = _one_off(client, TODAY - timedelta(days=3))
    newer = _one_off(client, TODAY - timedelta(days=1))

    moved = client.post("/app/api/plan/reschedule-missed").json()
    dates = {m["id"]: m["scheduled_date"] for m in moved}
    assert len(moved) == 2
    assert len(set(dates.values())) == 2  # never collide onto the same day
    assert dates[older["id"]] == TODAY.isoformat()  # oldest gets first pick
    assert dates[newer["id"]] == (TODAY + timedelta(days=1)).isoformat()


def test_hard_calendar_event_blocks_landing_on_or_adjacent_to_it(client):
    _hard_event(client, TODAY)  # hard hike today
    _one_off(client, TODAY - timedelta(days=1))

    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert len(moved) == 1
    # today-1 (already past), today, and today+1 are all blocked by the hike's
    # buffer -> earliest open day is today+2.
    assert moved[0]["scheduled_date"] == (TODAY + timedelta(days=2)).isoformat()


def test_moderate_calendar_event_does_not_block_landing(client):
    client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Rec league game",
            "template_key": "league_game",
            "regions": "legs",
            "intensity": "moderate",
            "duration_s": 3600,
            "started_at": datetime.combine(TODAY, datetime.min.time()).isoformat(),
        },
    )
    _one_off(client, TODAY - timedelta(days=1))
    moved = client.post("/app/api/plan/reschedule-missed").json()
    assert moved[0]["scheduled_date"] == TODAY.isoformat()
