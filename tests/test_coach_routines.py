"""Coach authoring routines: schema, synthesize/rewrite, grounding, e2e save."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from api.schemas.coach import (
    ExerciseProgression,
    ProgramSpec,
    RoutineExerciseSpec,
    RoutineSpec,
    ScheduleEntry,
)
from api.services.coach.agent import _validate_grounding
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
    materialize,
    rewrite_routine_refs,
    synthesize_routines,
)
from api.services.coach.objective_context import (
    CoachObjectiveContext,
    ExerciseCandidate,
)


# --------------------------------------------------------------------------- #
# schema: exactly-one target on schedule + progression
# --------------------------------------------------------------------------- #
def test_schedule_entry_requires_exactly_one_target():
    ScheduleEntry(template_id=1, weekday="monday")  # ok
    ScheduleEntry(routine_key="lower", weekday="monday")  # ok
    with pytest.raises(ValidationError):
        ScheduleEntry(weekday="monday")  # neither
    with pytest.raises(ValidationError):
        ScheduleEntry(template_id=1, routine_key="lower", weekday="monday")  # both


def test_progression_requires_exactly_one_target():
    ExerciseProgression(template_id=1)
    ExerciseProgression(routine_key="lower")
    with pytest.raises(ValidationError):
        ExerciseProgression()
    with pytest.raises(ValidationError):
        ExerciseProgression(template_id=1, routine_key="lower")


# --------------------------------------------------------------------------- #
# synthesize + rewrite (pure)
# --------------------------------------------------------------------------- #
def _routine_spec() -> ProgramSpec:
    return ProgramSpec(
        name="Baker Block",
        start_date=date(2026, 6, 29),  # Monday
        duration_weeks=4,
        new_routines=[
            RoutineSpec(
                key="lower",
                name="Lower + Carry",
                exercises=[
                    RoutineExerciseSpec(exercise_id=501, sets=3, reps=8, weight=95.0),
                    RoutineExerciseSpec(exercise_id=502, sets=3, duration_seconds=40),
                ],
            )
        ],
        schedule=[ScheduleEntry(routine_key="lower", weekday="monday")],
        progressions=[
            ExerciseProgression(routine_key="lower", exercise_id=501,
                                reps={"mode": "linear", "start": 8, "end": 4})
        ],
        deload_weeks=[4],
    )


_META = {501: ("Loaded Step-up", False), 502: ("Plank", True)}


def test_synthesize_routines_materializes_authored_routine():
    spec = _routine_spec()
    ctx = MaterializeContext(weight_unit="lb", templates={})
    mat_spec, mat_ctx = synthesize_routines(spec, ctx, _META)

    # the routine became a synthetic (negative-id) template; refs were rewritten
    assert mat_spec.new_routines == []
    sid = mat_spec.schedule[0].template_id
    assert sid is not None and sid < 0
    assert mat_spec.schedule[0].routine_key is None
    assert mat_spec.progressions[0].template_id == sid
    assert sid in mat_ctx.templates
    assert mat_ctx.templates[sid].exercises[0].name == "Loaded Step-up"

    workouts = materialize(mat_spec, mat_ctx)
    assert len(workouts) == 4  # 1 routine x 4 weeks
    assert all(w.scheduled_date.weekday() == 0 for w in workouts)  # Mondays
    by_week = {w.week_index: w for w in workouts}
    assert by_week[1].exercises[0].target_reps == 8
    assert by_week[4].exercises[0].target_reps == 4  # ramped down across the block
    # the timed exercise carries its duration, no reps
    assert by_week[1].exercises[1].target_duration_seconds == 40


def test_synthesize_noop_without_new_routines():
    spec = ProgramSpec(
        name="x", start_date=date(2026, 1, 5), duration_weeks=1,
        schedule=[ScheduleEntry(template_id=1, weekday="monday")],
    )
    ctx = MaterializeContext(weight_unit="lb", templates={})
    out_spec, out_ctx = synthesize_routines(spec, ctx, {})
    assert out_spec is spec and out_ctx is ctx


def test_rewrite_routine_refs_maps_keys_to_ids():
    spec = _routine_spec()
    out = rewrite_routine_refs(spec, {"lower": 77})
    assert out.new_routines == []
    assert out.schedule[0].template_id == 77 and out.schedule[0].routine_key is None
    assert out.progressions[0].template_id == 77


# --------------------------------------------------------------------------- #
# grounding
# --------------------------------------------------------------------------- #
def _ctx_with_template() -> MaterializeContext:
    return MaterializeContext(
        weight_unit="lb",
        templates={
            1: TemplateCtx(1, "Upper", [TemplateExerciseCtx(101, "Bench", False)])
        },
    )


def _obj_ctx_with_candidates() -> CoachObjectiveContext:
    return CoachObjectiveContext(
        candidates=[
            ExerciseCandidate(501, "Step-up", False, ["quads"], "dumbbell"),
            ExerciseCandidate(502, "Plank", True, ["core"], "body only"),
        ]
    )


def test_grounding_accepts_authored_routine_from_candidates():
    _validate_grounding(_routine_spec(), _ctx_with_template(), _obj_ctx_with_candidates())


def test_grounding_rejects_unknown_exercise_in_routine():
    spec = _routine_spec()
    spec.new_routines[0].exercises[0].exercise_id = 999999  # not a candidate/template
    with pytest.raises(ValueError, match="unknown exercise_id"):
        _validate_grounding(spec, _ctx_with_template(), _obj_ctx_with_candidates())


def test_grounding_rejects_schedule_to_undefined_routine_key():
    spec = _routine_spec()
    spec.schedule[0] = ScheduleEntry(routine_key="missing", weekday="monday")
    with pytest.raises(ValueError, match="undefined routine_key"):
        _validate_grounding(spec, _ctx_with_template(), _obj_ctx_with_candidates())


def test_grounding_allows_existing_template_exercise_id():
    # an authored routine may reuse an exercise from the user's existing template
    spec = _routine_spec()
    spec.new_routines[0].exercises = [RoutineExerciseSpec(exercise_id=101, sets=3, reps=5)]
    _validate_grounding(spec, _ctx_with_template(), _obj_ctx_with_candidates())


# --------------------------------------------------------------------------- #
# e2e: generate authors routines, save persists them as real templates
# --------------------------------------------------------------------------- #
class _FakeBlock:
    type = "tool_use"
    name = "emit_program_spec"

    def __init__(self, payload):
        self.input = payload


class _FakeResp:
    def __init__(self, payload):
        self.content = [_FakeBlock(payload)]


class _FakeClient:
    canned: dict = {}

    def __init__(self, **_kw):
        pass

    @property
    def messages(self):
        client = self

        class _M:
            def create(self, **_kw):
                return _FakeResp(client.canned)

        return _M()


def _install_fake(monkeypatch, payload):
    import anthropic

    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    _FakeClient.canned = payload
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)


def _set_alpine_objective(client):
    client.post(
        "/api/objectives",
        json={"name": "Climb Baker", "kind": "dated", "target_date": "2026-09-05",
              "sport": "alpine", "is_primary": True},
    )


def test_generate_and_save_authored_routine(client, monkeypatch):
    _set_alpine_objective(client)
    # a real catalog exercise that is in the alpine candidate pool ("step up")
    hits = client.get("/api/exercises/search", params={"q": "step up"}).json()
    ex_id = hits[0]["exercise"]["id"]

    canned = {
        "name": "Baker Block",
        "start_date": "2026-06-29",
        "duration_weeks": 4,
        "new_routines": [
            {
                "key": "lower",
                "name": "Lower + Carry",
                "exercises": [{"exercise_id": ex_id, "sets": 3, "reps": 8, "weight": 95}],
            }
        ],
        "schedule": [{"routine_key": "lower", "weekday": "monday"}],
        "progressions": [
            {"routine_key": "lower", "reps": {"mode": "linear", "start": 8, "end": 4}}
        ],
        "deload_weeks": [4],
        "coach_summary": "Authored a lower/carry day, periodized to the summit.",
    }
    _install_fake(monkeypatch, canned)

    # generate → preview shows the routine it will create + materialized workouts
    prev = client.post("/api/coach/generate", json={"message": "build my plan"})
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["created_routines"][0]["name"] == "Lower + Carry"
    assert len(body["planned_workouts"]) == 4

    # save → the routine becomes a real reusable template + the program schedules it
    saved = client.post("/api/coach/programs", json={"spec": body["spec"]})
    assert saved.status_code == 201, saved.text
    prog = saved.json()
    assert len(prog["planned_workouts"]) == 4
    new_tid = prog["planned_workouts"][0]["template_id"]
    assert new_tid is not None and new_tid > 0  # real id, not synthetic

    templates = client.get("/api/templates").json()
    assert any(t["name"] == "Lower + Carry" for t in templates)


def test_generate_works_with_objective_and_no_existing_routines(client, monkeypatch):
    # the whole point: a user with an objective but NO routines can still generate
    _set_alpine_objective(client)
    hits = client.get("/api/exercises/search", params={"q": "romanian deadlift"}).json()
    ex_id = hits[0]["exercise"]["id"]
    canned = {
        "name": "Block", "start_date": "2026-06-29", "duration_weeks": 2,
        "new_routines": [
            {
                "key": "post",
                "name": "Posterior",
                "exercises": [{"exercise_id": ex_id, "sets": 3, "reps": 8}],
            }
        ],
        "schedule": [{"routine_key": "post", "weekday": "monday"}],
        "progressions": [], "deload_weeks": [], "coach_summary": "go",
    }
    _install_fake(monkeypatch, canned)
    r = client.post("/api/coach/generate", json={"message": "plan me"})
    assert r.status_code == 200, r.text
    assert r.json()["created_routines"][0]["name"] == "Posterior"


def test_candidate_pool_populated_from_alpine_profile(client, db):
    from api.db.identity import ensure_dev_identity
    from api.services.coach.context import build_coach_objective_context

    _set_alpine_objective(client)
    ctx = build_coach_objective_context(db, ensure_dev_identity(db))
    assert ctx.candidates  # the alpine search_terms surfaced catalog exercises
    names = " ".join(c.name.lower() for c in ctx.candidates)
    assert "step" in names or "deadlift" in names or "calf" in names
