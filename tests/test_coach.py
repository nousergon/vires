"""AI coach: deterministic materializer (pure, no network) + mocked generate."""

from __future__ import annotations

from datetime import date

import pytest

from api.schemas.coach import (
    ExerciseProgression,
    ProgramSpec,
    ProgressionCurve,
    ScheduleEntry,
)
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
    end_date,
    materialize,
)


# --------------------------------------------------------------------------- #
# pure materializer
# --------------------------------------------------------------------------- #
def _ctx() -> MaterializeContext:
    return MaterializeContext(
        weight_unit="lb",
        templates={
            1: TemplateCtx(
                1,
                "Upper",
                [
                    TemplateExerciseCtx(
                        101, "Bench", False, target_sets=3, target_reps=10, target_weight=135.0
                    )
                ],
            ),
            2: TemplateCtx(
                2,
                "Lower",
                [
                    TemplateExerciseCtx(
                        201, "Squat", False, target_sets=3, target_reps=10, last_weight=185.0
                    )
                ],
            ),
        },
    )


def _spec() -> ProgramSpec:
    # Brian's canonical example: 2 routines, 1x/week, 8 weeks, reps 10->4,
    # weight ramps as % of start, deload week 4.
    return ProgramSpec(
        name="8-Week Block",
        start_date=date(2026, 6, 29),  # a Monday
        duration_weeks=8,
        schedule=[
            ScheduleEntry(template_id=1, weekday=0),  # Mon
            ScheduleEntry(template_id=2, weekday=3),  # Thu
        ],
        progressions=[
            ExerciseProgression(
                template_id=1,
                reps=ProgressionCurve(mode="linear", start=10, end=4),
                weight=ProgressionCurve(mode="percent_of_start", start=1.0, end=1.3),
            ),
            ExerciseProgression(
                template_id=2,
                reps=ProgressionCurve(mode="linear", start=10, end=4),
                weight=ProgressionCurve(mode="percent_of_start", start=1.0, end=1.25),
            ),
        ],
        deload_weeks=[4],
    )


def test_materialize_count_and_weekdays():
    pw = materialize(_spec(), _ctx())
    assert len(pw) == 16  # 2 templates x 8 weeks
    upper = [p for p in pw if p.template_id == 1]
    lower = [p for p in pw if p.template_id == 2]
    assert all(p.scheduled_date.weekday() == 0 for p in upper)  # Mondays
    assert all(p.scheduled_date.weekday() == 3 for p in lower)  # Thursdays
    assert upper[0].scheduled_date == date(2026, 6, 29)
    assert end_date(_spec()) == date(2026, 8, 20)


def test_reps_interpolate_down():
    upper = sorted(
        [p for p in materialize(_spec(), _ctx()) if p.template_id == 1],
        key=lambda p: p.week_index,
    )
    assert upper[0].exercises[0].target_reps == 10
    assert upper[-1].exercises[0].target_reps == 4
    # monotonic non-increasing across weeks
    reps = [p.exercises[0].target_reps for p in upper]
    assert reps == sorted(reps, reverse=True)


def test_weight_percent_ramp_rounds_to_plate():
    upper = sorted(
        [p for p in materialize(_spec(), _ctx()) if p.template_id == 1],
        key=lambda p: p.week_index,
    )
    assert upper[0].exercises[0].target_weight == 135.0  # 135 * 1.0
    assert upper[-1].exercises[0].target_weight == 175.0  # 135 * 1.3 = 175.5 -> 175.0
    for p in upper:
        w = p.exercises[0].target_weight
        assert round(w / 2.5) == w / 2.5  # every weight is a 2.5 lb multiple


def test_deload_week_is_lighter_and_noted():
    by_week = {p.week_index: p for p in materialize(_spec(), _ctx()) if p.template_id == 1}
    w3 = by_week[3].exercises[0].target_weight
    w4 = by_week[4].exercises[0].target_weight  # deload
    w5 = by_week[5].exercises[0].target_weight
    assert w4 < w3 and w4 < w5
    assert by_week[4].exercises[0].notes == "Deload"


def test_seed_weight_fallback_order():
    # template target_weight beats last_weight; explicit seed_weight beats both.
    ctx = MaterializeContext(
        weight_unit="lb",
        templates={
            1: TemplateCtx(
                1,
                "T",
                [
                    TemplateExerciseCtx(
                        101, "X", False, target_sets=1, target_reps=5,
                        target_weight=100.0, last_weight=80.0,
                    )
                ],
            )
        },
    )
    flat = ProgressionCurve(mode="percent_of_start", start=1.0, end=1.0)
    base = ProgramSpec(
        name="s", start_date=date(2026, 1, 5), duration_weeks=1,
        schedule=[ScheduleEntry(template_id=1, weekday=0)],
        progressions=[ExerciseProgression(template_id=1, weight=flat)],
    )
    assert materialize(base, ctx)[0].exercises[0].target_weight == 100.0  # target, not 80
    seeded = base.model_copy(
        update={
            "progressions": [
                ExerciseProgression(template_id=1, seed_weight=120.0, weight=flat)
            ]
        }
    )
    assert materialize(seeded, ctx)[0].exercises[0].target_weight == 120.0


def test_single_week_no_division_error():
    spec = ProgramSpec(
        name="1wk", start_date=date(2026, 1, 5), duration_weeks=1,
        schedule=[ScheduleEntry(template_id=1, weekday=0)],
        progressions=[
            ExerciseProgression(
                template_id=1, reps=ProgressionCurve(mode="linear", start=10, end=4)
            )
        ],
    )
    pw = materialize(spec, _ctx())
    assert len(pw) == 1
    assert pw[0].exercises[0].target_reps == 10  # f=0 -> start value


def test_kg_uses_smaller_plate_increment():
    ctx = _ctx()
    ctx.weight_unit = "kg"
    upper = sorted(
        [p for p in materialize(_spec(), ctx) if p.template_id == 1], key=lambda p: p.week_index
    )
    for p in upper:
        w = p.exercises[0].target_weight
        assert round(w / 1.25) == w / 1.25  # 1.25 kg multiples


# --------------------------------------------------------------------------- #
# /coach/generate with a mocked Anthropic client
# --------------------------------------------------------------------------- #
class _FakeBlock:
    type = "tool_use"
    name = "emit_program_spec"

    def __init__(self, payload: dict):
        self.input = payload


class _FakeResp:
    def __init__(self, payload: dict):
        self.content = [_FakeBlock(payload)]


class _FakeMessages:
    def create(self, **_kw):
        payload = _FakeClient.canned[min(_FakeClient.calls, len(_FakeClient.canned) - 1)]
        _FakeClient.calls += 1
        return _FakeResp(payload)


class _FakeClient:
    canned: list[dict] = []
    calls = 0

    def __init__(self, **_kw):
        pass

    @property
    def messages(self):
        return _FakeMessages()


def _install_fake(monkeypatch, canned: list[dict], key: str | None = "test-key"):
    import anthropic

    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", key)
    _FakeClient.canned = canned
    _FakeClient.calls = 0
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)


def _bench_template(client) -> tuple[int, int]:
    hits = client.get("/api/exercises/search", params={"q": "bench press"}).json()
    e1 = hits[0]["exercise"]["id"]
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Upper",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 10, "target_weight": 135}
            ],
        },
    ).json()
    return tpl["id"], e1


def _canned_spec(template_id: int, weeks: int = 4) -> dict:
    return {
        "name": "Test Block",
        "start_date": "2026-06-29",
        "duration_weeks": weeks,
        "schedule": [{"template_id": template_id, "weekday": 0}],
        "progressions": [
            {
                "template_id": template_id,
                "reps": {"mode": "linear", "start": 10, "end": 4},
                "weight": {"mode": "percent_of_start", "start": 1.0, "end": 1.3},
            }
        ],
        "deload_weeks": [],
        "coach_summary": "Four-week ramp from 10 to 4 reps.",
    }


def test_generate_returns_preview(client, monkeypatch):
    tpl_id, _ = _bench_template(client)
    _install_fake(monkeypatch, [_canned_spec(tpl_id, weeks=4)])
    resp = client.post("/api/coach/generate", json={"message": "4 weeks, 10 to 4 reps"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["planned_workouts"]) == 4
    assert body["coach_summary"].startswith("Four-week")
    assert body["planned_workouts"][0]["exercises"][0]["target_reps"] == 10
    assert body["planned_workouts"][-1]["exercises"][0]["target_reps"] == 4


def test_generate_retries_on_invalid_grounding(client, monkeypatch):
    tpl_id, _ = _bench_template(client)
    bad = _canned_spec(tpl_id)
    bad["schedule"] = [{"template_id": 999999, "weekday": 0}]  # unknown template -> retry
    good = _canned_spec(tpl_id)
    _install_fake(monkeypatch, [bad, good])
    resp = client.post("/api/coach/generate", json={"message": "go"})
    assert resp.status_code == 200, resp.text
    assert _FakeClient.calls == 2  # initial + one correction


def test_generate_503_without_key(client, monkeypatch):
    _bench_template(client)
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    resp = client.post("/api/coach/generate", json={"message": "anything"})
    assert resp.status_code == 503


def test_generate_400_without_templates(client, monkeypatch):
    _install_fake(monkeypatch, [_canned_spec(1)])  # key present, but no routines exist
    resp = client.post("/api/coach/generate", json={"message": "plan me"})
    assert resp.status_code == 400


def test_save_program_persists_and_materializes(client):
    tpl_id, _ = _bench_template(client)
    prog = client.post(
        "/api/coach/programs", json={"spec": _canned_spec(tpl_id, weeks=8)}
    ).json()
    assert len(prog["planned_workouts"]) == 8
    assert prog["status"] == "active"
    # reps + weight materialized on the persisted rows
    wk1 = prog["planned_workouts"][0]["exercises"][0]
    assert wk1["target_reps"] == 10 and wk1["target_weight"] == 135.0


@pytest.mark.parametrize("mode", ["linear", "constant", "step"])
def test_progression_modes_smoke(mode):
    ctx = _ctx()
    spec = ProgramSpec(
        name="m", start_date=date(2026, 1, 5), duration_weeks=4,
        schedule=[ScheduleEntry(template_id=1, weekday=0)],
        progressions=[
            ExerciseProgression(
                template_id=1, reps=ProgressionCurve(mode=mode, start=10, end=4, steps=4)
            )
        ],
    )
    pw = sorted(
        [p for p in materialize(spec, ctx) if p.template_id == 1], key=lambda p: p.week_index
    )
    assert pw[0].exercises[0].target_reps == 10
    if mode == "constant":
        assert all(p.exercises[0].target_reps == 10 for p in pw)
    else:
        assert pw[-1].exercises[0].target_reps == 4
