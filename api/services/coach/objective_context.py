"""Pure dataclasses the coach is grounded on for objective-driven generation.

Kept DB-free (like the materializer's context) so the agent can render them and
tests can build them without a database. ``context.py`` assembles these from the
ORM; ``agent.py`` renders them into the grounding block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ObjectiveCtx:
    """An objective the program peaks/tapers toward (the focus, or a timeline peak)."""

    name: str
    kind: str  # 'dated' | 'open_ended'
    target_date: date | None
    sport: str | None
    demands_profile: dict[str, Any] | None = None
    # The real objective id — the coach sets it on each season phase it builds.
    id: int | None = None
    # Last day of a multi-day event; training is skipped target_date..event_end_date.
    event_end_date: date | None = None
    # Sub-objectives (dated training milestones) nested under this objective —
    # benchmarks the coach periodizes a mini-taper/retest around inside the block.
    # Only populated for the focus objective. Each is itself an ObjectiveCtx.
    milestones: list[ObjectiveCtx] = field(default_factory=list)


@dataclass
class ConstraintCtx:
    """A bound the coach trains *around* (never a goal)."""

    kind: str  # 'injury' | 'schedule' | 'equipment'
    label: str
    directives: str | None
    defer_to_professional: bool = False


@dataclass
class ExerciseCandidate:
    """A real catalog exercise the coach may use to AUTHOR a new routine. The
    pool is assembled from the objective's needs-analysis so the right movements
    are available; grounding still only permits these real ids."""

    exercise_id: int
    name: str
    is_timed: bool
    primary_muscles: list[str]
    equipment: str | None


@dataclass
class CoachObjectiveContext:
    """The objective + active constraints generation runs against (may be empty)."""

    objective: ObjectiveCtx | None = None
    constraints: list[ConstraintCtx] = field(default_factory=list)
    # Catalog exercises the coach may author new routines from (objective-driven).
    candidates: list[ExerciseCandidate] = field(default_factory=list)
    # All dated objectives in chronological order (the peak timeline). ``objective``
    # is the focus (the soonest/next peak); ``timeline`` lets the coach periodize
    # toward the next peak while holding farther ones as base-building context.
    timeline: list[ObjectiveCtx] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.objective is None and not self.constraints
