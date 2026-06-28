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
    """The active primary objective the program peaks/tapers toward."""

    name: str
    kind: str  # 'dated' | 'open_ended'
    target_date: date | None
    sport: str | None
    demands_profile: dict[str, Any] | None = None


@dataclass
class ConstraintCtx:
    """A bound the coach trains *around* (never a goal)."""

    kind: str  # 'injury' | 'schedule' | 'equipment'
    label: str
    directives: str | None
    defer_to_professional: bool = False


@dataclass
class CoachObjectiveContext:
    """The objective + active constraints generation runs against (may be empty)."""

    objective: ObjectiveCtx | None = None
    constraints: list[ConstraintCtx] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.objective is None and not self.constraints
