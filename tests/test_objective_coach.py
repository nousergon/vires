"""Objective-driven generation: the objective + constraints reach the model,
and the public baseline prompt carries the schema mechanism + safety rules
(never the coaching methodology — see the public/private split, vires-ops#53)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from api.services.coach.agent import _context_block, _objective_block
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
)
from api.services.coach.objective_context import (
    ActivitySessionCtx,
    CoachObjectiveContext,
    ConstraintCtx,
    EventOccurrenceCtx,
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


def test_context_block_carries_preferred_weekdays_when_set():
    ctx = _mat_ctx()
    ctx.preferred_weekdays = ["monday", "thursday"]
    block = json.loads(_context_block(ctx, date(2026, 6, 28), None))
    assert block["preferred_weekdays"] == ["monday", "thursday"]


def test_context_block_omits_preferred_weekdays_when_unset():
    block = json.loads(_context_block(_mat_ctx(), date(2026, 6, 28), None))
    assert "preferred_weekdays" not in block


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
# athletic-event load-accounting: events reach the model as load constraints (#33)
# --------------------------------------------------------------------------- #
def _event_ctx(**over) -> EventOccurrenceCtx:
    kw = dict(
        name="Tuesday pickup soccer",
        template_key="league_game",
        occurrence_date=date(2026, 7, 7),
        sport="soccer",
        load={"regions": "legs", "intensity": "moderate", "duration_min": 90},
        recurrence="weekly",
    )
    kw.update(over)
    return EventOccurrenceCtx(**kw)


def test_objective_block_renders_events_as_load_constraints():
    ctx = CoachObjectiveContext(events=[_event_ctx()])
    block = _objective_block(ctx, date(2026, 6, 28))
    assert block is not None  # events alone still ground the coach
    ev = block["events"][0]
    assert ev["name"] == "Tuesday pickup soccer"
    assert ev["date"] == "2026-07-07"
    assert ev["load"] == {"regions": "legs", "intensity": "moderate", "duration_min": 90}
    assert ev["recurrence"] == "weekly"
    assert ev["weeks_away"] == 1  # 6/28 -> 7/7 = 9 days = 1 whole week
    # the coach is told this is trained-around load, not a goal
    assert "around" in ev["note"].lower() and "recovery budget" in ev["note"].lower()


def test_events_reach_the_grounding_context_even_without_an_objective():
    ctx = CoachObjectiveContext(events=[_event_ctx()])
    block = json.loads(_context_block(_mat_ctx(), date(2026, 6, 28), ctx))
    assert block["goal"]["events"][0]["name"] == "Tuesday pickup soccer"
    assert "objective" not in block["goal"]  # no goal, purely a load constraint


def test_objective_anchored_event_carries_its_objective_id():
    ctx = CoachObjectiveContext(events=[_event_ctx(recurrence="none", objective_id=42)])
    block = _objective_block(ctx, date(2026, 6, 28))
    assert block["events"][0]["objective_id"] == 42


def test_no_events_key_when_none_present():
    block = _objective_block(_obj_ctx(), date(2026, 6, 28))
    assert "events" not in block


def test_baseline_prompt_mentions_events_and_recent_activities_fields():
    """The public baseline must still READ every CONTEXT field mechanically
    (so a self-hosted deploy behaves correctly for a user with events/recent
    activities set) — but the load-accounting/fatigue-in HEURISTICS are the
    private coaching edge, not asserted here. See
    test_baseline_prompt_stays_generic_no_proprietary_methodology."""
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        assert "events" in text and "objective_id" in text
        assert "recent_activities" in text and "days_ago" in text
    finally:
        load_system_prompt.cache_clear()


# --------------------------------------------------------------------------- #
# DB integration: a logged recurring event reaches the coach context expanded
# --------------------------------------------------------------------------- #
def test_recurring_event_is_expanded_into_coach_context(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    # A weekly leg-heavy commitment anchored on an in-window Tuesday.
    r = client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Wednesday hoops",
            "template_key": "league_game",
            "regions": "legs",
            "intensity": "hard",
            "duration_s": 3600,
            "started_at": datetime.combine(date.today(), datetime.min.time()).isoformat(),
            "recurrence": "weekly",
        },
    )
    assert r.status_code == 201, r.text
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert ctx.events, "the recurring event should expand into the coach context"
    # weekly cadence => multiple in-window occurrences, all the same series
    assert {e.name for e in ctx.events} == {"Wednesday hoops"}
    assert len(ctx.events) >= 2
    assert all(e.recurrence == "weekly" for e in ctx.events)
    # occurrences arrive soonest-first and 7 days apart
    dates = [e.occurrence_date for e in ctx.events]
    assert dates == sorted(dates)
    assert (dates[1] - dates[0]).days == 7


# --------------------------------------------------------------------------- #
# generic activity logging: recent activities reach the model as ALREADY-
# ABSORBED load, distinct from events (upcoming load to train around)
# --------------------------------------------------------------------------- #
def _activity_ctx(**over) -> ActivitySessionCtx:
    kw = dict(
        name="Indoor top-rope",
        session_date=date(2026, 6, 27),
        regions="upper",
        intensity="hard",
        duration_min=90,
    )
    kw.update(over)
    return ActivitySessionCtx(**kw)


def test_objective_block_renders_recent_activities_as_absorbed_load():
    ctx = CoachObjectiveContext(recent_activities=[_activity_ctx()])
    block = _objective_block(ctx, date(2026, 6, 28))
    assert block is not None  # activities alone still ground the coach
    a = block["recent_activities"][0]
    assert a["name"] == "Indoor top-rope"
    assert a["date"] == "2026-06-27"
    assert a["days_ago"] == 1
    assert a["regions"] == "upper"
    assert a["intensity"] == "hard"
    assert a["duration_min"] == 90
    # the coach is told this is past load, not a constraint to schedule around
    assert "already" in a["note"].lower()
    assert "recover" in a["note"].lower()


def test_no_recent_activities_key_when_none_present():
    block = _objective_block(_obj_ctx(), date(2026, 6, 28))
    assert "recent_activities" not in block


def test_recent_activities_reach_the_grounding_context_even_without_an_objective():
    ctx = CoachObjectiveContext(recent_activities=[_activity_ctx()])
    block = json.loads(_context_block(_mat_ctx(), date(2026, 6, 28), ctx))
    assert block["goal"]["recent_activities"][0]["name"] == "Indoor top-rope"
    assert "objective" not in block["goal"]


def test_logged_activity_reaches_the_coach_context(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    r = client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Indoor top-rope",
            "template_key": "climbing_indoor_toprope",
            "regions": "upper",
            "intensity": "hard",
            "duration_s": 5400,
        },
    )
    assert r.status_code == 201, r.text
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert ctx.recent_activities, "the logged activity should reach the coach context"
    a = ctx.recent_activities[0]
    assert a.name == "Indoor top-rope"
    assert a.regions == "upper"
    assert a.intensity == "hard"
    assert a.duration_min == 90
    # The server stamps started_at with UTC "now" (api.routers.workouts._now),
    # not local wall-clock time — compare against the same clock to avoid a
    # spurious failure near local-midnight/UTC-date-rollover boundaries.
    assert a.session_date == datetime.now(UTC).date()


def test_activity_outside_the_lookback_window_does_not_reach_the_coach(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    r = client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Old swim",
            "regions": "full",
            "intensity": "light",
            "started_at": (date.today() - timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert ctx.recent_activities == []


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
    hits = client.get("/app/api/exercises/search", params={"q": "step up"}).json()
    ex_id = hits[0]["exercise"]["id"]
    tpl = client.post(
        "/app/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": ex_id, "target_sets": 3}]},
    ).json()
    # an active objective + constraint
    client.post(
        "/app/api/objectives",
        json={
            "name": "Climb Baker",
            "kind": "dated",
            "target_date": "2026-09-05",
            "sport": "alpine",
            "is_primary": True,
        },
    )
    client.post(
        "/app/api/constraints",
        json={
            "kind": "injury",
            "label": "recovering L4-L5 disc",
            "directives": "avoid heavy axial spinal loading",
        },
    )

    _install_capturing(monkeypatch, tpl["id"])
    r = client.post("/app/api/coach/generate", json={"message": "build my plan"})
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
    hits = client.get("/app/api/exercises/search", params={"q": "step up"}).json()
    ex_id = hits[0]["exercise"]["id"]
    tpl = client.post(
        "/app/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": ex_id, "target_sets": 3}]},
    ).json()
    # two dated peaks, neither pinned -> focus is derived as the soonest
    client.post(
        "/app/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2030-09-05",
              "sport": "alpine"},
    )
    client.post(
        "/app/api/objectives",
        json={"name": "Run a 50k", "kind": "dated", "target_date": "2030-07-15"},
    )

    _install_capturing(monkeypatch, tpl["id"])
    r = client.post("/app/api/coach/generate", json={"message": "build my plan"})
    assert r.status_code == 200, r.text

    user_text = _CapturingClient.captured[0]["messages"][0]["content"]
    payload = json.loads(user_text.split("CONTEXT:\n", 1)[1].split("\n\nREQUEST:", 1)[0])
    goal = payload["goal"]
    # focus = the nearer peak; the timeline carries both, chronologically
    assert goal["objective"]["name"] == "Run a 50k"
    assert [p["name"] for p in goal["timeline"]] == ["Run a 50k", "Climb Baker"]


# --------------------------------------------------------------------------- #
# the public baseline prompt carries the mechanism (never the methodology) —
# see the public/private split note in prompt_loader.py + vires-ops#53.
# --------------------------------------------------------------------------- #
def test_baseline_prompt_has_objective_awareness_and_safety_language():
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        assert "target_date" in text  # reads the objective's date
        assert "deload_weeks" in text  # schema mechanism
        assert "never prescribe" in text  # injury safety (always public — never traded for IP)
        assert "pt/physician" in text or "physician" in text  # defer to professional
        assert "demands_profile" in text  # reads the needs-analysis field
    finally:
        load_system_prompt.cache_clear()


def test_baseline_prompt_stays_generic_no_proprietary_methodology():
    """Guards the public/private split (2026-07-08, vires-ops#53): the
    committed baseline is a competent-but-generic example — the actual
    coaching depth (periodization phase sequencing, event/cross-training
    load-accounting heuristics, the season-phase algorithm's specific
    transition rules) lives ONLY in the private tuned prompt
    (vires-ops/prompts/coach_system.txt, hydrated via SSM), never here."""
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        for phrase in [
            "max strength",
            "muscular-endurance conversion",
            "load-accounting",
            "load accounting",
            "already spent",  # fatigue-in accounting
            "freshest",  # recovery-around heuristic
            "sport-specific",  # season-phase sequencing language
        ]:
            assert phrase not in text, (
                f"proprietary coaching methodology leaked into the public "
                f"baseline: {phrase!r}"
            )
    finally:
        load_system_prompt.cache_clear()


def test_generate_accepts_and_materializes_a_phased_season(client, monkeypatch):
    """End-to-end: the model sees the timeline (with objective_id + event window)
    and emits a phased season; grounding accepts it and the materializer expands
    both blocks."""
    import anthropic

    from api.config import get_settings

    e = client.get("/app/api/exercises/search", params={"q": "step up"}).json()[0]["exercise"]["id"]
    tpl = client.post(
        "/app/api/templates",
        json={"name": "Lower", "exercises": [{"exercise_id": e, "target_sets": 3}]},
    ).json()
    o1 = client.post(
        "/app/api/objectives",
        json={"name": "Baker", "kind": "dated", "target_date": "2030-06-23",
              "event_end_date": "2030-06-25", "sport": "alpine"},
    ).json()
    o2 = client.post(
        "/app/api/objectives",
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

    r = client.post("/app/api/coach/generate", json={"message": "plan my whole season"})
    assert r.status_code == 200, r.text
    # both blocks materialized (2 weeks each)
    assert len(r.json()["planned_workouts"]) == 4
    # the model was handed the timeline with the data needed to phase-plan
    user_text = captured[0]["messages"][0]["content"]
    assert '"event_end_date": "2030-06-25"' in user_text
    assert f'"objective_id": {o1["id"]}' in user_text


def test_baseline_prompt_knows_to_use_phases_for_a_multi_peak_timeline():
    """Schema mechanism, not strategy: with 2+ dated peaks the coach must use
    ProgramSpec's `phases` field instead of a flat `schedule`, or a self-hosted
    multi-objective season silently collapses to nonsense. The actual block-
    sequencing/transition RULES are the private edge — not asserted here."""
    from api.services.coach.prompt_loader import load_system_prompt

    load_system_prompt.cache_clear()
    text = load_system_prompt().lower()
    try:
        assert "phases" in text and "objective_id" in text  # emit phased spec
    finally:
        load_system_prompt.cache_clear()


# --------------------------------------------------------------------------- #
# merged-model split: an upcoming (not yet closed out) activity is an "event"
# constraint; an already-closed-out one is "recent_activities" absorbed load —
# never both. There's no stored status; this is derived purely from
# started_at/ended_at vs. "now" (merge_calendar_events_into_activity).
# --------------------------------------------------------------------------- #
def test_future_activity_is_an_event_not_a_recent_activity(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Boston Marathon",
            "template_key": "race",
            "regions": "legs",
            "intensity": "hard",
            "started_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        },
    )
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert any(e.name == "Boston Marathon" for e in ctx.events)
    assert not any(a.name == "Boston Marathon" for a in ctx.recent_activities)


def test_closed_out_past_activity_is_recent_not_an_event(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    client.post(
        "/app/api/workouts/activity",
        json={
            "name": "Morning run",
            "template_key": "run",
            "regions": "legs",
            "intensity": "moderate",
        },
    )
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert any(a.name == "Morning run" for a in ctx.recent_activities)
    assert not any(e.name == "Morning run" for e in ctx.events)
