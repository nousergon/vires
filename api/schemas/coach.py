"""AI-coach schemas.

The coach is a *grounded structured-output agent*: the LLM emits a declarative
``ProgramSpec`` (schedule + progression curves), and deterministic Python
(``api.services.coach.materialize``) expands it into concrete dated workouts. The
LLM never computes per-week reps/weight — that is deterministic, testable, and
reproducible. These models are also the tool-use ``input_schema`` the model is
forced to emit (see ``api.services.coach.agent``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Weekday = Literal[
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]
_DAY_NAMES: tuple[str, ...] = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
)
# Accept full + 3-letter names (any case) and map to canonical lowercase.
_DAY_ALIASES = {name: name for name in _DAY_NAMES}
_DAY_ALIASES.update({name[:3]: name for name in _DAY_NAMES})

# --------------------------------------------------------------------------- #
# Declarative spec (the coach's forced tool-use output)
# --------------------------------------------------------------------------- #
ProgressionMode = str  # 'linear' | 'step' | 'constant' | 'percent_of_start'


class ProgressionCurve(BaseModel):
    """How a single metric (reps or weight) moves from week 1 to the final week.

    ``start``/``end`` are the values at the first and last week. For a *weight*
    curve with ``mode='percent_of_start'`` they are multipliers on the resolved
    seed weight (e.g. 1.0 -> 1.30 = +30%); otherwise they are absolute values.
    """

    mode: str = Field(
        default="linear",
        description="linear | step | constant | percent_of_start",
    )
    start: float = Field(description="value at week 1")
    end: float = Field(description="value at the final week")
    steps: int | None = Field(
        default=None,
        description="for mode='step': number of discrete levels (default = duration_weeks)",
    )


class ExerciseProgression(BaseModel):
    """A progression rule for one exercise (or all exercises in a routine).

    Targets either an existing ``template_id`` OR a new routine the coach is
    defining in this spec, by its ``routine_key`` (exactly one)."""

    template_id: int | None = None
    routine_key: str | None = Field(
        default=None, description="key of a new_routines entry this rule applies to"
    )
    exercise_id: int | None = Field(
        default=None, description="None = applies to every exercise in the routine"
    )
    sets: int | None = Field(default=None, description="fixed sets; None keeps the routine's")
    reps: ProgressionCurve | None = None
    weight: ProgressionCurve | None = None
    seed_weight: float | None = Field(
        default=None,
        description="starting weight when the routine/history has none",
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> ExerciseProgression:
        if (self.template_id is None) == (self.routine_key is None):
            raise ValueError("set exactly one of template_id or routine_key")
        return self


class RoutineExerciseSpec(BaseModel):
    """One exercise in a routine the coach is defining (real catalog id)."""

    exercise_id: int
    sets: int | None = Field(default=None, description="working sets")
    reps: int | None = Field(default=None, description="target reps (omit for timed holds)")
    weight: float | None = Field(default=None, description="starting weight, if known")
    duration_seconds: int | None = Field(
        default=None, description="hold seconds for a timed exercise (e.g. plank)"
    )
    rest_seconds: int | None = None


class RoutineSpec(BaseModel):
    """A NEW routine the coach authors so the plan can train the objective even
    when the user has no suitable existing routine. Referenced from schedule /
    progressions by ``key`` and persisted as a reusable WorkoutTemplate on save."""

    key: str = Field(description="local reference within this spec, e.g. 'lower_carry'")
    name: str = Field(description="routine name, e.g. 'Lower Body + Loaded Carries'")
    exercises: list[RoutineExerciseSpec] = Field(
        description="ordered exercises (real exercise_id from the catalog only)"
    )


class ScheduleEntry(BaseModel):
    """Run a routine once per week on ``weekday`` (a lowercase day name). The
    routine is either an existing ``template_id`` OR a new one the coach defines
    in this spec, by its ``routine_key`` (exactly one).

    The model emits a NAME ('monday') rather than an index — having the LLM do
    0-vs-1 weekday math was unreliable (it used ISO Monday=1, shifting every
    workout +1 day). The validator also coerces a legacy int (0=Mon … 6=Sun) from
    older stored specs so they still load.
    """

    template_id: int | None = None
    routine_key: str | None = Field(
        default=None, description="key of a new_routines entry to schedule"
    )
    weekday: Weekday

    @field_validator("weekday", mode="before")
    @classmethod
    def _normalize_weekday(cls, v: object) -> object:
        if isinstance(v, bool):  # guard: bool is an int subclass
            return v
        if isinstance(v, int):
            return _DAY_NAMES[v % 7]
        if isinstance(v, str):
            return _DAY_ALIASES.get(v.strip().lower(), v.strip().lower())
        return v

    @model_validator(mode="after")
    def _exactly_one_target(self) -> ScheduleEntry:
        if (self.template_id is None) == (self.routine_key is None):
            raise ValueError("set exactly one of template_id or routine_key")
        return self


class ProgramSpec(BaseModel):
    name: str = Field(description="short program name, e.g. '8-Week Strength Block'")
    start_date: date = Field(description="ISO date the program begins")
    duration_weeks: int = Field(ge=1, le=52)
    new_routines: list[RoutineSpec] = Field(
        default_factory=list,
        description="routines the coach authors for this objective (persisted on save)",
    )
    schedule: list[ScheduleEntry] = Field(
        description="one entry per (routine, weekday) the user trains each week"
    )
    progressions: list[ExerciseProgression] = Field(default_factory=list)
    deload_weeks: list[int] = Field(
        default_factory=list, description="1-based week numbers to deload (~-10% load)"
    )
    coach_summary: str = Field(
        default="", description="plain-English explanation of the plan for the user"
    )


# --------------------------------------------------------------------------- #
# API request / response models
# --------------------------------------------------------------------------- #
class GenerateRequest(BaseModel):
    message: str = Field(min_length=1)
    # The prior spec, resent for a refine turn ("make week 4 a deload").
    prior_spec: ProgramSpec | None = None


class PlannedExercisePreview(BaseModel):
    exercise_id: int
    exercise_name: str
    order_index: int
    target_sets: int | None = None
    target_reps: int | None = None
    target_weight: float | None = None
    target_duration_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None


class PlannedWorkoutPreview(BaseModel):
    template_id: int | None
    scheduled_date: date
    name: str
    week_index: int | None
    exercises: list[PlannedExercisePreview]


class CreatedRoutinePreview(BaseModel):
    """A routine the coach will create on confirm (shown so the user knows new
    routines are being authored, not just scheduled)."""

    key: str
    name: str
    exercise_names: list[str]


class ProgramPreview(BaseModel):
    """Non-persisted result of /coach/generate — the spec + its materialization."""

    name: str
    coach_summary: str
    start_date: date
    end_date: date
    weight_unit: str
    spec: ProgramSpec
    planned_workouts: list[PlannedWorkoutPreview]
    created_routines: list[CreatedRoutinePreview] = Field(default_factory=list)


class SaveProgramRequest(BaseModel):
    spec: ProgramSpec
    name: str | None = None
    goal_text: str | None = None


class ModifyRequest(BaseModel):
    """A natural-language change to an existing program ('shift a week', 'deload wk4')."""

    message: str = Field(min_length=1)


class ProgramModifyPreview(BaseModel):
    """Non-persisted preview of a modification: the proposed new plan + what it does
    to the existing program. Completed workouts are always preserved; only future
    (not-yet-done) workouts are replaced when applied."""

    program_id: int
    preview: ProgramPreview
    completed_preserved: int  # completed workouts that stay frozen
    future_count: int  # new future workouts that will be scheduled (>= today)


class ReplanTriggerOut(BaseModel):
    """One structural reason the coach suggests re-planning."""

    kind: str  # missed_sessions | plan_exhausted | objective_passed | objective_changed
    reason: str


class ReplanCheckOut(BaseModel):
    """Cheap (no-LLM) answer to 'should this plan be re-planned?' — gates the
    expensive proposal so the UI only offers a re-plan when something fired."""

    suggested: bool
    triggers: list[ReplanTriggerOut]


class ReplanProposal(BaseModel):
    """A proposed (non-persisted) auto re-plan: why it fired + the modification
    preview. Applied via PUT /coach/programs/{id} (propose-and-confirm; never
    auto-applied)."""

    triggers: list[ReplanTriggerOut]
    modification: ProgramModifyPreview


class PlanChangeEventOut(BaseModel):
    """One row of the plan-change audit trail (autoregulation or revision)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    program_id: int | None
    session_id: int | None
    source: str  # autoregulation | plan_revision
    trigger: str | None
    summary: str
    detail: dict | None
    created_at: datetime


class TranscribeOut(BaseModel):
    text: str
