"""ICS calendar feed: pure builder + feed-url minting + the public .ics endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime

from api.services.ics import IcsEvent, build_calendar


def _ex_id(client, q: str) -> int:
    return client.get("/app/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


# --------------------------------------------------------------------------- #
# pure builder
# --------------------------------------------------------------------------- #
def test_build_calendar_structure_and_escaping():
    ev = IcsEvent(
        uid="planned-1@vires.nousergon.ai",
        start=date(2026, 7, 1),
        summary="Upper, Heavy; week 1",  # comma + semicolon must be escaped
        description="Bench: 3×10 @ 135lb\nRow: 3×10",  # newline -> \n
        dtstamp=datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC),
    )
    ics = build_calendar("Vires Workouts", [ev])
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20260701" in ics
    assert "DTEND;VALUE=DATE:20260702" in ics  # all-day exclusive end
    assert "SUMMARY:Upper\\, Heavy\\; week 1" in ics
    assert "\\n" in ics  # newline escaped, not a literal break inside the value
    assert "\r\n" in ics  # CRLF line endings


def test_build_calendar_multi_day_event_end_is_exclusive():
    ev = IcsEvent(
        uid="trip@vires", start=date(2026, 7, 9), end=date(2026, 7, 11),
        summary="Baker", description="", dtstamp=datetime(2026, 6, 1, tzinfo=UTC),
    )
    ics = build_calendar("Cal", [ev])
    assert "DTSTART;VALUE=DATE:20260709" in ics
    assert "DTEND;VALUE=DATE:20260712" in ics  # 7/11 inclusive -> 7/12 exclusive end


def test_build_calendar_folds_long_lines():
    ev = IcsEvent(
        uid="x@vires",
        start=date(2026, 7, 1),
        summary="S",
        description="word " * 60,  # ~300 chars -> must fold to <=75-octet lines
        dtstamp=datetime(2026, 6, 28, tzinfo=UTC),
    )
    ics = build_calendar("Cal", [ev])
    assert all(len(line.encode("utf-8")) <= 75 for line in ics.split("\r\n"))
    assert "\r\n " in ics  # a continuation line (leading space)


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
def test_feed_url_mints_token_and_is_stable(client):
    r1 = client.get("/app/api/plan/feed-url").json()
    assert r1["token"] and r1["ics_path"] == f"/app/api/plan/feed/{r1['token']}.ics"
    r2 = client.get("/app/api/plan/feed-url").json()
    assert r2["token"] == r1["token"]  # idempotent


def test_rotate_changes_token_and_invalidates_old(client):
    old = client.get("/app/api/plan/feed-url").json()["token"]
    new = client.post("/app/api/plan/feed-url/rotate").json()["token"]
    assert new != old
    assert client.get(f"/app/api/plan/feed/{old}.ics").status_code == 404
    assert client.get(f"/app/api/plan/feed/{new}.ics").status_code == 200


def test_feed_bad_token_404(client):
    assert client.get("/app/api/plan/feed/not-a-real-token.ics").status_code == 404


def test_feed_includes_planned_and_adhoc_sessions(client):
    e1 = _ex_id(client, "bench press")
    tpl = client.post(
        "/app/api/templates",
        json={
            "name": "Upper",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 10, "target_weight": 135}
            ],
        },
    ).json()
    client.post(
        "/app/api/plan/planned", json={"scheduled_date": "2026-07-01", "template_id": tpl["id"]}
    )

    # a finished ad-hoc session (no plan link)
    ws = client.post("/app/api/workouts", json={"name": "Leg Day"}).json()
    se = client.post(f"/app/api/workouts/{ws['id']}/exercises", json={"exercise_id": e1}).json()
    sets_url = f"/app/api/workouts/{ws['id']}/exercises/{se['id']}/sets"
    client.post(sets_url, json={"reps": 5, "weight": 225})
    client.post(f"/app/api/workouts/{ws['id']}/finish")

    token = client.get("/app/api/plan/feed-url").json()["token"]
    resp = client.get(f"/app/api/plan/feed/{token}.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert body.count("BEGIN:VEVENT") == 2  # 1 planned + 1 ad-hoc session
    assert "SUMMARY:Upper" in body
    assert "SUMMARY:✓ Leg Day" in body  # completed session marked done
    assert "DTSTART;VALUE=DATE:20260701" in body


def test_feed_excludes_in_progress_adhoc(client):
    # An unfinished ad-hoc workout should not clutter the calendar.
    client.post("/app/api/workouts", json={"name": "Unfinished"})
    token = client.get("/app/api/plan/feed-url").json()["token"]
    body = client.get(f"/app/api/plan/feed/{token}.ics").text
    assert "Unfinished" not in body


def test_feed_includes_dated_objectives_as_peaks(client):
    # A dated objective shows on the subscribed calendar as an all-day peak marker.
    client.post(
        "/app/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2026-09-05",
              "sport": "alpine"},
    )
    # an open-ended objective must NOT appear (no date to anchor)
    client.post(
        "/app/api/objectives",
        json={"name": "General health", "kind": "open_ended", "sport": None},
    )
    token = client.get("/app/api/plan/feed-url").json()["token"]
    body = client.get(f"/app/api/plan/feed/{token}.ics").text
    assert "SUMMARY:🎯 Climb Baker" in body
    assert "DTSTART;VALUE=DATE:20260905" in body
    assert "General health" not in body


def test_feed_event_band_spans_a_multi_day_event(client):
    client.post(
        "/app/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-07-09",
              "event_end_date": "2030-07-11", "sport": "alpine"},
    )
    token = client.get("/app/api/plan/feed-url").json()["token"]
    body = client.get(f"/app/api/plan/feed/{token}.ics").text
    assert "SUMMARY:🎯 Baker" in body
    assert "DTSTART;VALUE=DATE:20300709" in body
    assert "DTEND;VALUE=DATE:20300712" in body  # 7/9–7/11 inclusive event band


def test_feed_block_band_and_workout_labels_for_objective(client):
    e = client.get(
        "/app/api/exercises/search", params={"q": "bench press"}
    ).json()[0]["exercise"]["id"]
    tpl = client.post(
        "/app/api/templates",
        json={"name": "Alpine", "exercises": [{"exercise_id": e, "target_sets": 3,
              "target_reps": 5, "target_weight": 100}]},
    ).json()
    o = client.post(
        "/app/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-07-09", "sport": "alpine"},
    ).json()
    spec = {
        "name": "Season",
        "phases": [
            {"objective_id": o["id"], "start_date": "2030-06-01", "duration_weeks": 3,
             "schedule": [{"template_id": tpl["id"], "weekday": "monday"}]},
        ],
    }
    client.post("/app/api/coach/programs", json={"spec": spec})
    token = client.get("/app/api/plan/feed-url").json()["token"]
    body = client.get(f"/app/api/plan/feed/{token}.ics").text
    # the training block shows as its own labeled band
    assert "Baker — alpine block" in body
    # each attributed workout is labeled with its objective
    assert "For: Baker" in body
