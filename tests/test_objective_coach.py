"""Objective-driven generation: the objective + constraints reach the model,
and the public baseline prompt carries the periodization + safety rules."""

from __future__ import annotations

import json
from datetime import date

from api.services.coach.agent import _context_block, _objective_block
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
)
from api.services.coach.objective_context import (
    CoachObjectiveContext,
    ConstraintCtx,
    ObjectiveCtx,
)
from api.services.coach.objective_profiles import (
    ALPINE_DEMANDS_PROFILE,
    LUMBAR_DISC_DIRECTIVES,
)


def _mat_ctx() -> MaterializeContext:
    return MaterializeContext(
        weight_unit="lb",
        templates={
            1: TemplateCtx(
                1, "Lower", [TemplateExerciseCtx(101, "Step-up", False, target_sets=3)]
            )
        },
    )


def _obj_ctx() -> CoachObjectiveContext:
    return CoachObjectiveContext(
        objective=ObjectiveCtx(
            name="Climb Baker",
            kind="dated",
            target_date=date(2026, 9, 5),
            sport="alpine",
            demands_profile=ALPINE_DEMANDS_PROFILE,
        ),
        constraints=[
            ConstraintCtx(
                kind="injury",
                label="recovering L4-L5 disc",
                directives=LUMBAR_DISC_DIRECTIVES,
                defer_to_professional=True,
            )
        ],
    )


# --------------------------------------------------------------------------- #
# the objective + constraints are rendered into the grounding context
# --------------------------------------------------------------------------- #
def test_context_block_includes_objective_and_constraints():
    block = json.loads(_context_block(_mat_ctx(), date(2026, 6, 28), _obj_ctx()))
    goal = block["goal"]
    assert goal["objective"]["name"] == "Climb Baker"
    assert goal["objective"]["target_date"] == "2026-09-05"
    assert goal["objective"]["sport"] == "alpine"
    # the authored alpine emphasis travels as data
    emphasis = " ".join(goal["objective"]["demands_profile"]["exercise_emphasis"]).lower()
    assert "step-up" in emphasis
    # the disc directives are present so the model can train around it
    assert goal["constraints"][0]["label"] == "recovering L4-L5 disc"
    assert "axial" in goal["constraints"][0]["directives"].lower()
    assert goal["constraints"][0]["defer_to_professional"] is True


def test_objective_block_computes_weeks_until_target():
    block = _objective_block(_obj_ctx(), date(2026, 8, 1))
    # 2026-08-01 -> 2026-09-05 is 35 days = 5 weeks
    assert block["objective"]["weeks_until_target"] == 5


def _multi_obj_ctx() -> CoachObjectiveContext:
    """Two dated peaks: a nearer 50k (the focus) and a farther alpine climb (a
    multi-day event)."""
    near = ObjectiveCtx(
        id=10, name="Run a 50k", kind="dated", target_date=date(2026, 7, 15), sport=None
    )
    far = ObjectiveCtx(
        id=20,
        name="Climb Baker",
        kind="dated",
        target_date=date(2026, 9, 5),
        event_end_date=date(2026, 9, 7),
        sport="alpine",
        demands_profile=ALPINE_DEMANDS_PROFILE,
    )
    return CoachObjectiveContext(objective=near, timeline=[near, far])


def test_objective_block_renders_timeline_for_multiple_peaks():
    block = _objective_block(_multi_obj_ctx(), date(2026, 6, 28))
    # focus = the nearer peak
    assert block["objective"]["name"] == "Run a 50k"
    # the full timeline travels, chronologically, with weeks-to-each + the data
    # the coach needs to build a phase per peak (id + event window)
    tl = block["timeline"]
    assert [p["name"] for p in tl] == ["Run a 50k", "Climb Baker"]
    assert [p["objective_id"] for p in tl] == [10, 20]
    assert tl[0]["weeks_until_target"] == 2  # 6/28 -> 7/15 = 17 days
    assert tl[1]["weeks_until_target"] == 9  # 6/28 -> 9/5 = 69 days = 9 whole weeks
    assert tl[1]["sport"] == "alpine"
    assert tl[1]["event_end_date"] == "2026-09-07"


def test_single_objective_block_has_no_timeline_key():
    # _obj_ctx() has the default empty timeline -> no redundant "timeline" block
    block = _objective_block(_obj_ctx(), date(2026, 6, 28))
    assert "timeline" not in block


def _obj_ctx_with_milestone() -> CoachObjectiveContext:
    """Focus objective (Climb Baker, 9/5) with one training milestone nested in
    its block (Mailbox Peak, 8/1)."""
    milestone = ObjectiveCtx(
        id=30,
        name="Mailbox Peak",
        kind="dated",
        target_date=date(2026, 8, 1),
        sport="alpine",
    )
    focus = ObjectiveCtx(
        id=20,
        name="Climb Baker",
        kind="dated",
        target_date=date(2026, 9, 5),
        sport="alpine",
        demands_profile=ALPINE_DEMANDS_PROFILE,
        milestones=[milestone],
    )
    return CoachObjectiveContext(objective=focus)


def test_objective_block_renders_milestones_inside_the_block():
    block = _objective_block(_obj_ctx_with_milestone(), date(2026, 6, 28))
    # the milestone rides inside the focus objective, NOT as a separate peak
    assert "timeline" not in block
    ms = block["objective"]["milestones"]
    assert [m["name"] for m in ms] == ["Mailbox Peak"]
    assert ms[0]["objective_id"] == 30
    assert ms[0]["weeks_until_target"] == 4  # 6/28 -> 8/1 = 34 days = 4 whole weeks
    # the coach is told to treat it as a mid-block checkpoint, not the goal
    assert "checkpoint" in ms[0]["note"]


def test_objective_block_no_milestones_key_when_none():
    block = _objective_block(_obj_ctx(), date(2026, 6, 28))
    assert "milestones" not in block["objective"]


def test_no_goal_key_when_objective_context_empty():
    block = json.loads(_context_block(_mat_ctx(), date(2026, 6, 28), None))
    assert "goal" not in block
    empty = json.loads(
        _context_block(_mat_ctx(), date(2026, 6, 28), CoachObjectiveContext())
    )
    assert "goal" not in empty


# --------------------------------------------------------------------------- #
# end-to-end: /api/coach/generate feeds the active objective to the model
# --------------------------------------------------------------------------- #
class _CapturingMessages:
    def create(self, **kw):
        _CapturingClient.captured.append(kw)
        payload = {
            "name": "Baker Block",
            "start_date": "2026-06-29",
            "duration_weeks": 4,
            "schedule": [{"template_id": _CapturingClient.tpl_id, "weekday": "monday"}],
            "progressions": [],
            "deload_weeks": [4],
            "coach_summary": "Periodized to the summit; final week tapers.",
        }

        class _Block:
            type = "tool_use"
            name = "emit_program_spec"
            input = payload

        class _Resp:
            content = [_Block()]

        return _Resp()


class _CapturingClient:
    captured: list[dict] = []
    tpl_id = 0

    def __init__(self, **_kw):
        pass

    @property
    def messages(self):
        return _CapturingMessages()


def _install_capturing(monkeypatch, tpl_id: int):
    import anthropic

    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    _CapturingClient.captured = []
    _CapturingClient.tpl_id = tpl_id
    monkeypatch.setattr(anthropic, "Anthropic", _CapturingClient)


def test_generate_feeds_active_objective_and_constraint(client, monkeypatch):
    # a template to ground on
    hits = client.get("/api/exercises/search", params={"q": "step up"}).json()
    ex_id = hits[0]["exercise"]["id"]
    tpl = client.post(
        "/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": ex_id, "target_sets": 3}]},
    ).json()
    # an active objective + constraint
    client.post(
        "/api/objectives",
        json={
            "name": "Climb Baker",
            "kind": "dated",
            "target_date": "2026-09-05",
            "sport": "alpine",
            "is_primary": True,
        },
    )
    client.post(
        "/api/constraints",
        json={
            "kind": "injury",
            "label": "recovering L4-L5 disc",
            "directives": "avoid heavy axial spinal loading",
        },
    )

    _install_capturing(monkeypatch, tpl["id"])
    r = client.post("/api/coach/generate", json={"message": "build my plan"})
    assert r.status_code == 200, r.text

    # the model saw the objective + constraint in its user message
    user_text = _CapturingClient.captured[0]["messages"][0]["content"]
    assert "Climb Baker" in user_text
    assert "2026-09-05" in user_text
    assert "recovering L4-L5 disc" in user_text
    assert "axial" in user_text.lower()


def test_generate_feeds_full_dated_timeline(client, monkeypatch):
    """With two dated objectives, the model sees the timeline (both peaks),
    focused on the nearer one. Far-future dates keep 'upcoming' run-date-stable."""
    hits = client.get("/api/exercises/search", params={"q": "step up"}).json()
    ex_id = hits[0]["exercise"]["id"]
    tpl = client.post(
        "/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": ex_id, "target_sets": 3}]},
    ).json()
    # two dated peaks, neither pinned -> focus is derived as the soonest
    client.post(
        "/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2030-09-05",
              "sport": "alpine"},
    )
    client.post(
        "/api/objectives",
        json={"name": "Run a 50k", "kind": "dated", "target_date": "2030-07-15"},
    )

    _install_capturing(monkeypatch, tpl["id"])
    r = client.post("/api/coach/generate", json={"message": "build my plan"})
    assert r.status_code == 200, r.text

    user_text = _CapturingClient.captured[0]["messages"][0]["content"]
    payload = json.loads(user_text.split("CONTEXT:\n", 1)[1].split("\n\nREQUEST:", 1)[0])
    goal = payload["goal"]
    # focus = the nearer peak; the timeline carries both, chronologically
    assert goal["objective"]["name"] == "Run a 50k"
    assert [p["name"] for p in goal["timeline"]] == ["Run a 50k", "Climb Baker"]


# --------------------------------------------------------------------------- #
# the public baseline prompt carries the new rules
# --------------------------------------------------------------------------- #
def test_baseline_prompt_has_periodization_and_safety_language():
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        assert "target_date" in text and "taper" in text  # periodize-to-date
        assert "deload_weeks" in text  # taper mechanism
        assert "never prescribe" in text  # injury safety
        assert "pt/physician" in text or "physician" in text  # defer to professional
        assert "demands_profile" in text  # honor the needs-analysis
    finally:
        load_system_prompt.cache_clear()


def test_generate_accepts_and_materializes_a_phased_season(client, monkeypatch):
    """End-to-end: the model sees the timeline (with objective_id + event window)
    and emits a phased season; grounding accepts it and the materializer expands
    both blocks."""
    import anthropic

    from api.config import get_settings

    e = client.get("/api/exercises/search", params={"q": "step up"}).json()[0]["exercise"]["id"]
    tpl = client.post(
        "/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": e, "target_sets": 3}]},
    ).json()
    o1 = client.post(
        "/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-06-23",
              "event_end_date": "2030-06-25", "sport": "alpine"},
    ).json()
    o2 = client.post(
        "/api/objectives",
        json={"name": "Kangaroo Temple", "kind": "dated", "target_date": "2030-07-21"},
    ).json()

    phased = {
        "name": "Cascades season",
        "phases": [
            {"objective_id": o1["id"], "start_date": "2030-06-03", "duration_weeks": 2,
             "schedule": [{"template_id": tpl["id"], "weekday": "monday"}]},
            {"objective_id": o2["id"], "start_date": "2030-06-29", "duration_weeks": 2,
             "schedule": [{"template_id": tpl["id"], "weekday": "monday"}]},
        ],
        "coach_summary": "alpine then rock",
    }

    captured: list[dict] = []

    class _Msgs:
        def create(self, **kw):
            captured.append(kw)

            class _B:
                type = "tool_use"
                name = "emit_program_spec"
                input = phased

            class _R:
                content = [_B()]

            return _R()

    class _Cli:
        def __init__(self, **_kw):
            pass

        @property
        def messages(self):
            return _Msgs()

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", _Cli)

    r = client.post("/api/coach/generate", json={"message": "plan my whole season"})
    assert r.status_code == 200, r.text
    # both blocks materialized (2 weeks each)
    assert len(r.json()["planned_workouts"]) == 4
    # the model was handed the timeline with the data needed to phase-plan
    user_text = captured[0]["messages"][0]["content"]
    assert '"event_end_date": "2030-06-25"' in user_text
    assert f'"objective_id": {o1["id"]}' in user_text


def test_baseline_prompt_has_season_phase_language():
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        assert "season" in text  # plans the whole season up front
        assert "phases" in text and "objective_id" in text  # emit phased spec
        assert "event_end_date" in text  # chain blocks past the multi-day event
        assert "sport-specific" in text  # each block specific to its objective
    finally:
        load_system_prompt.cache_clear()
