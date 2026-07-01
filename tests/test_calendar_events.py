"""CalendarEvent API: CRUD, validation, and server-side weekly recurrence
expansion within a date window (vires-ops#31 — 'Closes when' explicitly names
the recurring-expansion test)."""

from __future__ import annotations

from datetime import date

from api.db.models import CalendarEvent


def _mk_event(client, **over):
    body = {
        "name": "Tuesday pickup soccer",
        "sport": None,
        "type": "league",
        "event_date": "2026-07-07",  # a Tuesday
        "recurrence": "weekly",
        "load": {"regions": "legs", "intensity": "moderate", "duration_min": 90},
    }
    body.update(over)
    return client.post("/api/calendar-events", json=body)


# --------------------------------------------------------------------------- #
# CRUD happy path
# --------------------------------------------------------------------------- #
def test_create_calendar_event_happy_path(client):
    r = _mk_event(client)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["name"] == "Tuesday pickup soccer"
    assert e["type"] == "league"
    assert e["recurrence"] == "weekly"
    assert e["load"] == {
        "regions": "legs",
        "intensity": "moderate",
        "duration_min": 90,
    }
    assert e["objective_id"] is None
    assert e["event_end_date"] is None


def test_list_calendar_events(client):
    _mk_event(client, name="A")
    _mk_event(client, name="B", recurrence="none")
    events = client.get("/api/calendar-events").json()
    assert {e["name"] for e in events} == {"A", "B"}


def test_get_calendar_event(client):
    e = _mk_event(client).json()
    r = client.get(f"/api/calendar-events/{e['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == e["id"]


def test_get_missing_calendar_event_404s(client):
    assert client.get("/api/calendar-events/99999").status_code == 404


def test_patch_calendar_event(client):
    e = _mk_event(client).json()
    r = client.patch(
        f"/api/calendar-events/{e['id']}",
        json={"notes": "bring shin guards", "load": {"regions": "full", "intensity": "hard"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notes"] == "bring shin guards"
    assert body["load"] == {"regions": "full", "intensity": "hard", "duration_min": None}


def test_delete_calendar_event(client):
    e = _mk_event(client).json()
    assert client.delete(f"/api/calendar-events/{e['id']}").status_code == 204
    assert client.get(f"/api/calendar-events/{e['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_invalid_type_rejected(client):
    r = _mk_event(client, type="marathon")  # not in the enum
    assert r.status_code == 422


def test_invalid_load_regions_rejected(client):
    r = _mk_event(client, load={"regions": "arms", "intensity": "hard"})
    assert r.status_code == 422


def test_event_end_date_before_event_date_rejected_on_create(client):
    r = _mk_event(
        client,
        recurrence="none",
        event_date="2026-08-10",
        event_end_date="2026-08-05",
    )
    assert r.status_code == 422


def test_event_end_date_before_event_date_rejected_on_patch(client):
    e = _mk_event(client, recurrence="none", event_date="2026-08-10").json()
    r = client.patch(
        f"/api/calendar-events/{e['id']}", json={"event_end_date": "2026-08-05"}
    )
    assert r.status_code == 400


def test_objective_id_must_exist(client):
    r = _mk_event(client, objective_id=99999)
    assert r.status_code == 404


def test_objective_id_anchors_event_when_provided(client):
    obj = client.post(
        "/api/objectives",
        json={"name": "Race day", "kind": "dated", "target_date": "2026-09-01"},
    ).json()
    r = _mk_event(
        client,
        name="Race day",
        type="competition",
        recurrence="none",
        event_date="2026-09-01",
        objective_id=obj["id"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["objective_id"] == obj["id"]


def test_deleting_objective_nulls_event_anchor(client, db):
    obj = client.post(
        "/api/objectives",
        json={"name": "Race day", "kind": "dated", "target_date": "2026-09-01"},
    ).json()
    e = _mk_event(
        client,
        name="Race day",
        type="competition",
        recurrence="none",
        event_date="2026-09-01",
        objective_id=obj["id"],
    ).json()
    assert client.delete(f"/api/objectives/{obj['id']}").status_code == 204
    row = db.get(CalendarEvent, e["id"])
    db.refresh(row)
    assert row.objective_id is None


# --------------------------------------------------------------------------- #
# server-side weekly recurrence expansion (the named "Closes when" case)
# --------------------------------------------------------------------------- #
def test_weekly_event_expands_to_correct_dates_in_window(client):
    # Anchored on a Tuesday; window spans ~5 weeks.
    _mk_event(client, name="Tuesday league", event_date="2026-07-07")

    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-01", "end": "2026-08-04"},
    )
    assert r.status_code == 200, r.text
    occ = r.json()
    dates = [o["occurrence_date"] for o in occ]
    # Every Tuesday from 2026-07-07 through 2026-08-04 inclusive.
    assert dates == ["2026-07-07", "2026-07-14", "2026-07-21", "2026-07-28", "2026-08-04"]
    assert all(o["event"]["name"] == "Tuesday league" for o in occ)


def test_weekly_event_window_excludes_occurrences_outside_range(client):
    _mk_event(client, name="Tuesday league", event_date="2026-07-07")

    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-15", "end": "2026-07-20"},
    )
    assert r.status_code == 200, r.text
    # No Tuesday falls inside 07-15..07-20 (07-14 and 07-21 are outside it).
    assert r.json() == []


def test_weekly_event_anchor_before_window_still_aligns_correctly(client):
    # Regression for off-by-one-week drift when the anchor is far before the
    # window: the first in-window occurrence must still land ON a real
    # multiple of 7 days from event_date, not merely >= window_start.
    _mk_event(client, name="Tuesday league", event_date="2026-01-06")  # a Tuesday

    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-01", "end": "2026-07-15"},
    )
    dates = [o["occurrence_date"] for o in r.json()]
    for d in dates:
        delta = (date.fromisoformat(d) - date(2026, 1, 6)).days
        assert delta % 7 == 0
    assert dates == ["2026-07-07", "2026-07-14"]


def test_one_off_event_yields_single_occurrence_in_window(client):
    _mk_event(
        client,
        name="5k race",
        type="competition",
        recurrence="none",
        event_date="2026-07-11",
    )
    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-01", "end": "2026-07-31"},
    )
    occ = r.json()
    assert len(occ) == 1
    assert occ[0]["occurrence_date"] == "2026-07-11"
    assert occ[0]["occurrence_end_date"] is None


def test_one_off_multiday_event_included_when_span_intersects_window(client):
    _mk_event(
        client,
        name="Ski trip",
        type="travel",
        recurrence="none",
        event_date="2026-12-28",
        event_end_date="2027-01-02",
        load={"regions": "legs", "intensity": "moderate"},
    )
    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-12-30", "end": "2027-01-05"},
    )
    occ = r.json()
    assert len(occ) == 1
    assert occ[0]["occurrence_date"] == "2026-12-28"
    assert occ[0]["occurrence_end_date"] == "2027-01-02"


def test_one_off_event_excluded_when_outside_window(client):
    _mk_event(
        client,
        name="Old race",
        type="competition",
        recurrence="none",
        event_date="2026-01-01",
    )
    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-01", "end": "2026-07-31"},
    )
    assert r.json() == []


def test_window_end_before_start_rejected(client):
    r = client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-31", "end": "2026-07-01"},
    )
    assert r.status_code == 400


def test_recurrence_not_persisted_as_extra_rows(client, db):
    _mk_event(client, name="Tuesday league", event_date="2026-07-07")
    client.get(
        "/api/calendar-events/window",
        params={"start": "2026-07-01", "end": "2026-09-01"},
    )
    # Expanding a window query must not materialize occurrence rows.
    assert db.query(CalendarEvent).count() == 1
