"""Phased season spec: the materializer expands consecutive objective blocks,
attributes each workout, and leaves the inter-objective event gap empty.
vires-ops#22.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from api.schemas.coach import ProgramPhase, ProgramSpec, ScheduleEntry
from api.services.coach.materialize import (
    MaterializeContext,
    TemplateCtx,
    TemplateExerciseCtx,
    end_date,
    materialize,
    start_date_of,
)


def _ctx() -> MaterializeContext:
    return MaterializeContext(
        weight_unit="lb",
        templates={
            1: TemplateCtx(
                1, "Alpine",
                [TemplateExerciseCtx(101, "Step-up", False, target_sets=3,
                                     target_reps=10, target_weight=40.0)],
            ),
            2: TemplateCtx(
                2, "Rock",
                [TemplateExerciseCtx(201, "Pull-up", False, target_sets=3, target_reps=8)],
            ),
        },
    )


def _season() -> ProgramSpec:
    # Baker block (obj 10): Mondays from 1/7/2030 for 2 weeks (peak ~1/14).
    # Kangaroo Temple block (obj 20): Mondays from 2/4/2030 for 2 weeks.
    # The gap 1/15..2/3 is the event + transition — no training.
    return ProgramSpec(
        name="2030 alpine season",
        phases=[
            ProgramPhase(
                objective_id=10, name="Baker — alpine", start_date=date(2030, 1, 7),
                duration_weeks=2, schedule=[ScheduleEntry(template_id=1, weekday="monday")],
            ),
            ProgramPhase(
                objective_id=20, name="Kangaroo Temple — rock", start_date=date(2030, 2, 4),
                duration_weeks=2, schedule=[ScheduleEntry(template_id=2, weekday="monday")],
            ),
        ],
    )


def test_phased_materializes_two_attributed_blocks():
    out = materialize(_season(), _ctx())
    baker = [w for w in out if w.objective_id == 10]
    kt = [w for w in out if w.objective_id == 20]
    assert len(baker) == 2 and len(kt) == 2
    # right routine per block
    assert all(w.template_id == 1 for w in baker)
    assert all(w.template_id == 2 for w in kt)
    # week_index resets per block
    assert sorted(w.week_index for w in baker) == [1, 2]
    assert sorted(w.week_index for w in kt) == [1, 2]
    # dates land in each block's window
    assert [w.scheduled_date for w in baker] == [date(2030, 1, 7), date(2030, 1, 14)]
    assert [w.scheduled_date for w in kt] == [date(2030, 2, 4), date(2030, 2, 11)]


def test_event_gap_between_blocks_has_no_workouts():
    out = materialize(_season(), _ctx())
    in_gap = [w for w in out if date(2030, 1, 15) <= w.scheduled_date <= date(2030, 2, 3)]
    assert in_gap == []


def test_phased_start_and_end_span_the_whole_season():
    spec = _season()
    assert start_date_of(spec) == date(2030, 1, 7)
    assert end_date(spec) == date(2030, 2, 11)


def test_flat_spec_workouts_have_no_objective_id():
    flat = ProgramSpec(
        name="flat", start_date=date(2030, 1, 7), duration_weeks=2,
        schedule=[ScheduleEntry(template_id=1, weekday="monday")],
    )
    out = materialize(flat, _ctx())
    assert out and all(w.objective_id is None for w in out)


def test_spec_with_neither_phases_nor_schedule_is_rejected():
    with pytest.raises(ValidationError):
        ProgramSpec(name="empty")


def test_flat_spec_without_start_date_is_rejected():
    with pytest.raises(ValidationError):
        ProgramSpec(name="x", schedule=[ScheduleEntry(template_id=1, weekday="monday")])
