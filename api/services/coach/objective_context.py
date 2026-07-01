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
class EventOccurrenceCtx:
    """One concrete occurrence of an athletic event the coach trains *around*
    (a load constraint, never a goal — the load-accounting axis, #33).

    Recurring (``weekly``) events are expanded server-side into one entry per
    in-window occurrence, so every entry here is a single concrete date the
    coach can schedule around."""

    name: str
    type: str  # 'competition' | 'league' | 'recreation' | 'travel' | 'rehab'
    occurrence_date: date
    # Last day of this occurrence (multi-day one-off events only; None otherwise).
    occurrence_end_date: date | None = None
    sport: str | None = None
    # Coarse structured load estimate: {'regions','intensity','duration_min'}.
    load: dict[str, Any] | None = None
    # 'none' | 'weekly' — 'weekly' means this is one occurrence of a STANDING
    # weekly commitment, so its debit belongs in the base weekly template.
    recurrence: str = "none"
    # Set when the event IS a peak target anchored to an objective — then it
    # rides that objective's taper instead of being a pure load constraint.
    objective_id: int | None = None
    notes: str | None = None


@dataclass
class ActivitySessionCtx:
    """A recently logged generic activity (climbing, swimming, yoga, ...) —
    already-absorbed training load the coach factors into today's fatigue/
    recovery reasoning, distinct from ``EventOccurrenceCtx`` (upcoming load to
    train *around*). Same coarse regions/intensity vocabulary as event load."""

    name: str
    session_date: date
    regions: str
    intensity: str
    duration_min: int | None = None


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
    # Upcoming athletic events (recurrence-expanded, within the planning window),
    # in chronological order — load constraints the coach trains *around*.
    events: list[EventOccurrenceCtx] = field(default_factory=list)
    # Recently logged generic activities (most recent first) — load already
    # absorbed, distinct from `events` (upcoming load to train around).
    recent_activities: list[ActivitySessionCtx] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        # Events/activities alone (no objective, no constraints) still warrant
        # grounding — the coach must account for their load even absent a goal.
        return (
            self.objective is None
            and not self.constraints
            and not self.events
            and not self.recent_activities
        )
