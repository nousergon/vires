"""Macro re-plan endpoints: cheap check gates the proposal; proposal is
propose-only (nothing persisted until PUT). vires-ops#9.
"""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/app/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _spec(template_id: int) -> dict:
    return {
        "name": "8wk",
        "start_date": "2030-01-07",  # far-future Monday: fresh plan is all-upcoming
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


def _make_missed(client, prog, n: int = 2) -> None:
    """Push the first n planned workouts into the past (still 'planned') so they
    register as missed — deterministic regardless of test run date."""
    for i in range(n):
        pid = prog["planned_workouts"][i]["id"]
        client.patch(f"/app/api/plan/planned/{pid}", json={"scheduled_date": f"2020-01-0{i + 1}"})


# --------------------------------------------------------------------------- #
# replan-check (no LLM)
# --------------------------------------------------------------------------- #
def test_fresh_plan_not_suggested(client):
    prog, _ = _program(client)
    r = client.get(f"/app/api/coach/programs/{prog['id']}/replan-check").json()
    assert r["suggested"] is False and r["triggers"] == []


def test_missed_sessions_suggested(client):
    prog, _ = _program(client)
    _make_missed(client, prog, 2)
    r = client.get(f"/app/api/coach/programs/{prog['id']}/replan-check").json()
    assert r["suggested"] is True
    assert "missed_sessions" in {t["kind"] for t in r["triggers"]}


def test_replan_check_404_for_unknown_program(client):
    assert client.get("/app/api/coach/programs/99999/replan-check").status_code == 404


def test_severity_seven_check_in_suggests_ailment_changed(client):
    """vires-ops#50: a severity-7 check-in on an open episode fires
    ailment_changed through the replan-check endpoint (not just the pure
    evaluate_triggers unit test in test_replan.py)."""
    prog, _ = _program(client)
    ep = client.post(
        "/app/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 2},
    ).json()
    client.post(f"/app/api/ailments/{ep['id']}/check-ins", json={"severity": 7})

    r = client.get(f"/app/api/coach/programs/{prog['id']}/replan-check").json()
    assert r["suggested"] is True
    assert "ailment_changed" in {t["kind"] for t in r["triggers"]}


# --------------------------------------------------------------------------- #
# replan (LLM proposal)
# --------------------------------------------------------------------------- #
def test_replan_409_when_nothing_fired(client):
    prog, _ = _program(client)
    r = client.post(f"/app/api/coach/programs/{prog['id']}/replan")
    assert r.status_code == 409  # no LLM call when no trigger


class _MockMessages:
    spec: dict = {}

    def create(self, **_kw):
        class _Block:
            type = "tool_use"
            name = "emit_program_spec"
            input = _MockMessages.spec

        class _Resp:
            content = [_Block()]

        return _Resp()


class _MockClient:
    def __init__(self, **_kw):
        pass

    @property
    def messages(self):
        return _MockMessages()


def test_replan_proposes_but_does_not_persist(client, monkeypatch):
    import anthropic

    from api.config import get_settings

    prog, tpl_id = _program(client)
    _make_missed(client, prog, 2)
    before = client.get("/app/api/plan/programs").json()

    # mock the coach to emit a valid grounded spec for this program's template
    _MockMessages.spec = _spec(tpl_id)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", _MockClient)

    r = client.post(f"/app/api/coach/programs/{prog['id']}/replan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "missed_sessions" in {t["kind"] for t in body["triggers"]}
    assert body["modification"]["program_id"] == prog["id"]
    assert body["modification"]["preview"]["spec"]["name"] == "8wk"

    # propose-only: the stored program is untouched until PUT
    after = client.get("/app/api/plan/programs").json()
    bp = next(p for p in before if p["id"] == prog["id"])
    ap = next(p for p in after if p["id"] == prog["id"])
    assert ap["planned_count"] == bp["planned_count"]
