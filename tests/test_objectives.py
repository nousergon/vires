"""Objectives + constraints API: CRUD, one-primary enforcement, defaults."""

from __future__ import annotations


def _mk_objective(client, **over):
    body = {
        "name": "Climb Baker",
        "kind": "dated",
        "target_date": "2026-09-05",
        "sport": "alpine",
        "is_primary": True,
    }
    body.update(over)
    return client.post("/api/objectives", json=body)


# --------------------------------------------------------------------------- #
# objectives
# --------------------------------------------------------------------------- #
def test_create_objective_autofills_alpine_demands(client):
    r = _mk_objective(client)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["sport"] == "alpine" and o["is_primary"] is True
    # the authored needs-analysis was filled from the sport
    assert o["demands_profile"] is not None
    assert o["demands_profile"]["sport"] == "alpine"
    joined = " ".join(o["demands_profile"]["exercise_emphasis"]).lower()
    assert "step-up" in joined and "eccentric" in joined


def test_dated_objective_requires_target_date(client):
    r = _mk_objective(client, target_date=None)
    assert r.status_code == 422  # schema validation


def test_open_ended_objective_allows_no_date(client):
    r = _mk_objective(client, kind="open_ended", target_date=None, sport=None)
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "open_ended"


def test_only_one_primary_enforced_on_create(client):
    a = _mk_objective(client, name="Climb Baker").json()
    b = _mk_objective(client, name="Run a 50k").json()
    objs = client.get("/api/objectives").json()
    primaries = [o for o in objs if o["is_primary"]]
    assert len(primaries) == 1 and primaries[0]["id"] == b["id"]
    # the first one was demoted
    assert next(o for o in objs if o["id"] == a["id"])["is_primary"] is False


def test_patch_set_primary_demotes_others(client):
    a = _mk_objective(client, name="Climb Baker").json()
    b = _mk_objective(client, name="Run a 50k").json()  # b is now primary
    # promote a back to primary
    r = client.patch(f"/api/objectives/{a['id']}", json={"is_primary": True})
    assert r.status_code == 200, r.text
    objs = {o["id"]: o for o in client.get("/api/objectives").json()}
    assert objs[a["id"]]["is_primary"] is True
    assert objs[b["id"]]["is_primary"] is False


def test_patch_dated_without_date_rejected(client):
    o = _mk_objective(client, kind="open_ended", target_date=None, sport=None).json()
    r = client.patch(f"/api/objectives/{o['id']}", json={"kind": "dated"})
    assert r.status_code == 400  # merged row would be dated with no target_date


def test_patch_sport_refreshes_demands_profile(client):
    o = _mk_objective(client, sport=None, demands_profile=None).json()
    assert o["demands_profile"] is None
    r = client.patch(f"/api/objectives/{o['id']}", json={"sport": "alpine"})
    assert r.json()["demands_profile"]["sport"] == "alpine"


def test_delete_objective(client):
    o = _mk_objective(client).json()
    assert client.delete(f"/api/objectives/{o['id']}").status_code == 204
    assert client.get(f"/api/objectives/{o['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# constraints
# --------------------------------------------------------------------------- #
def test_injury_constraint_defaults_defer_to_professional(client):
    r = client.post(
        "/api/constraints",
        json={"kind": "injury", "label": "recovering L4-L5 disc", "directives": "avoid axial load"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["defer_to_professional"] is True


def test_non_injury_constraint_does_not_defer(client):
    r = client.post("/api/constraints", json={"kind": "equipment", "label": "no barbell"})
    assert r.json()["defer_to_professional"] is False


def test_constraint_explicit_defer_override(client):
    r = client.post(
        "/api/constraints",
        json={"kind": "injury", "label": "tweaked wrist", "defer_to_professional": False},
    )
    assert r.json()["defer_to_professional"] is False


def test_deactivate_constraint_drops_it_from_active(client):
    c = client.post("/api/constraints", json={"kind": "schedule", "label": "MWF only"}).json()
    client.patch(f"/api/constraints/{c['id']}", json={"is_active": False})
    active = client.get("/api/objectives/active").json()
    assert all(x["id"] != c["id"] for x in active["constraints"])


# --------------------------------------------------------------------------- #
# active endpoint
# --------------------------------------------------------------------------- #
def test_active_endpoint_returns_primary_and_constraints(client):
    _mk_objective(client)
    client.post(
        "/api/constraints",
        json={"kind": "injury", "label": "recovering L4-L5 disc"},
    )
    active = client.get("/api/objectives/active").json()
    assert active["objective"]["name"] == "Climb Baker"
    assert len(active["constraints"]) == 1
    assert active["constraints"][0]["label"] == "recovering L4-L5 disc"


def test_active_endpoint_empty_when_unset(client):
    active = client.get("/api/objectives/active").json()
    assert active["objective"] is None and active["constraints"] == []
    assert active["objectives"] == []


# --------------------------------------------------------------------------- #
# multiple objectives: derived focus + timeline + priority
# (far-future dates so "upcoming" holds regardless of test run date)
# --------------------------------------------------------------------------- #
def test_active_focus_is_soonest_upcoming_dated(client):
    far = _mk_objective(
        client, name="Climb Baker", target_date="2030-12-01", is_primary=False
    ).json()
    soon = _mk_objective(
        client, name="Run a 50k", target_date="2030-07-15", is_primary=False, sport=None
    ).json()
    active = client.get("/api/objectives/active").json()
    # focus = the soonest upcoming peak
    assert active["objective"]["id"] == soon["id"]
    # timeline carries both, chronologically
    assert [o["id"] for o in active["objectives"]] == [soon["id"], far["id"]]


def test_active_primary_overrides_derived_focus(client):
    far = _mk_objective(
        client, name="Climb Baker", target_date="2030-12-01", is_primary=True
    ).json()
    _mk_objective(
        client, name="Run a 50k", target_date="2030-07-15", is_primary=False, sport=None
    )
    active = client.get("/api/objectives/active").json()
    assert active["objective"]["id"] == far["id"]  # the manual pin wins


def test_create_and_patch_priority(client):
    o = _mk_objective(client, priority=5).json()
    assert o["priority"] == 5
    r = client.patch(f"/api/objectives/{o['id']}", json={"priority": 9})
    assert r.status_code == 200 and r.json()["priority"] == 9


# --------------------------------------------------------------------------- #
# multi-day events (event_end_date)
# --------------------------------------------------------------------------- #
def test_create_objective_with_event_end_date(client):
    o = _mk_objective(
        client, target_date="2026-07-09", event_end_date="2026-07-11"
    ).json()
    assert o["target_date"] == "2026-07-09" and o["event_end_date"] == "2026-07-11"


def test_event_end_before_target_rejected(client):
    r = _mk_objective(client, target_date="2026-07-09", event_end_date="2026-07-05")
    assert r.status_code == 422  # schema validation


def test_event_end_without_target_rejected(client):
    r = _mk_objective(
        client, kind="open_ended", target_date=None, sport=None,
        event_end_date="2026-07-11",
    )
    assert r.status_code == 422


def test_patch_event_end_date_validated_against_merged_row(client):
    o = _mk_objective(client, target_date="2026-07-09").json()
    ok = client.patch(
        f"/api/objectives/{o['id']}", json={"event_end_date": "2026-07-11"}
    )
    assert ok.status_code == 200 and ok.json()["event_end_date"] == "2026-07-11"
    bad = client.patch(
        f"/api/objectives/{o['id']}", json={"event_end_date": "2026-07-01"}
    )
    assert bad.status_code == 400  # before target_date, merged-row check
