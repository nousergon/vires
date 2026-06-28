"""AI-coach schemas.

The coach is a *grounded structured-output agent*: the LLM emits a declarative
``ProgramSpec`` (schedule + progression curves), and deterministic Python
(``api.services.coach.materialize``) expands it into concrete dated workouts. The
LLM never computes per-week reps/weight — that is deterministic, testable, and
reproducible. These models are also the tool-use ``input_schema`` the model is
forced to emit (see ``api.services.coach.agent``).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

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
    """A progression rule for one exercise (or all exercises in a template)."""

    template_id: int
    exercise_id: int | None = Field(
        default=None, description="None = applies to every exercise in the template"
    )
    sets: int | None = Field(default=None, description="fixed sets; None keeps the template's")
    reps: ProgressionCurve | None = None
    weight: ProgressionCurve | None = None
    seed_weight: float | None = Field(
        default=None,
        description="starting weight when the template/history has none",
    )


class ScheduleEntry(BaseModel):
    """Run ``template_id`` once per week on ``weekday`` (0=Mon … 6=Sun)."""

    template_id: int
    weekday: int = Field(ge=0, le=6)


class ProgramSpec(BaseModel):
    name: str = Field(description="short program name, e.g. '8-Week Strength Block'")
    start_date: date = Field(description="ISO date the program begins")
    duration_weeks: int = Field(ge=1, le=52)
    schedule: list[ScheduleEntry] = Field(
        description="one entry per (template, weekday) the user wants each week"
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


class ProgramPreview(BaseModel):
    """Non-persisted result of /coach/generate — the spec + its materialization."""

    name: str
    coach_summary: str
    start_date: date
    end_date: date
    weight_unit: str
    spec: ProgramSpec
    planned_workouts: list[PlannedWorkoutPreview]


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


class TranscribeOut(BaseModel):
    text: str
