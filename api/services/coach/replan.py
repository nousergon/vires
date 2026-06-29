"""Macro re-plan triggers — the event-driven half of post-workout adaptation.

The *micro* loop (``autoregulate``) silently nudges loads every workout. This
*macro* loop watches for **structural** events that mean the plan's shape is
stale — missed sessions, the plan running out, the objective passing or
changing — and, when one fires, the coach **proposes** a re-plan the user must
confirm (never silent; reuses the existing modify→PUT cutover). See vires-ops#9.

Detection is deterministic and fed entirely by in-app data we already own.
``evaluate_triggers`` is pure (no DB) so it is unit-testable; ``detect_triggers``
is the thin DB wrapper. Generating the actual proposal (the LLM call) is left to
the router so detection stays cheap — the frontend checks first, then asks for a
proposal only when a trigger fired.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.db.identity import Identity
from api.db.models import Objective, Program
from api.services.objective_focus import effective_end, resolve_focus_objective

# Past planned-but-never-started sessions before a re-plan is suggested.
MISSED_SESSIONS_THRESHOLD = 2


@dataclass(frozen=True)
class ReplanTrigger:
    kind: str  # missed_sessions | plan_exhausted | objective_passed | objective_changed
    reason: str  # plain-English, shown to the user


def evaluate_triggers(
    planned: Iterable,
    *,
    program_objectives: list[Objective],
    focus_objective: Objective | None,
    today: date,
    missed_threshold: int = MISSED_SESSIONS_THRESHOLD,
) -> list[ReplanTrigger]:
    """Which structural re-plan triggers have fired (pure).

    Season-aware: ``program_objectives`` is EVERY objective the program trains
    for (its season blocks), not a single one — so a passed block fires while
    later blocks remain, and a newly-added focus the season doesn't cover fires
    objective_changed."""
    planned = list(planned)
    triggers: list[ReplanTrigger] = []

    missed = [pw for pw in planned if pw.scheduled_date < today and pw.status == "planned"]
    if len(missed) >= missed_threshold:
        triggers.append(
            ReplanTrigger(
                "missed_sessions",
                f"{len(missed)} planned sessions have passed without being done.",
            )
        )

    future_planned = [
        pw for pw in planned if pw.scheduled_date >= today and pw.status == "planned"
    ]
    if not future_planned:
        triggers.append(
            ReplanTrigger("plan_exhausted", "No upcoming workouts remain in this plan.")
        )

    # A block is done once its objective's event has passed (use the event end,
    # not just the peak, so a multi-day trip isn't "passed" while you're on it).
    passed = [
        o
        for o in program_objectives
        if o.kind == "dated" and o.target_date is not None and effective_end(o) < today
    ]
    if passed:
        names = ", ".join(f"'{o.name}'" for o in passed)
        triggers.append(
            ReplanTrigger(
                "objective_passed",
                f"You've finished {names} — refresh the rest of your season.",
            )
        )

    # A new focus the season doesn't yet train for (e.g. an objective added after
    # the plan was built).
    program_ids = {o.id for o in program_objectives}
    if focus_objective is not None and focus_objective.id not in program_ids:
        triggers.append(
            ReplanTrigger(
                "objective_changed",
                "A new focus objective isn't covered by this plan yet.",
            )
        )

    return triggers


def detect_triggers(
    db: Session, ident: Identity, program: Program, today: date | None = None
) -> list[ReplanTrigger]:
    """DB-backed trigger detection for a program."""
    if today is None:
        today = date.today()
    # Every objective the program trains for: its legacy single link + every
    # season-block objective its planned workouts are attributed to.
    ids: set[int] = set()
    if program.objective_id is not None:
        ids.add(program.objective_id)
    ids.update(pw.objective_id for pw in program.planned_workouts if pw.objective_id)
    program_objs = [o for o in (db.get(Objective, i) for i in ids) if o is not None]
    focus = resolve_focus_objective(db, ident, today)
    return evaluate_triggers(
        program.planned_workouts,
        program_objectives=program_objs,
        focus_objective=focus,
        today=today,
    )


def replan_instruction(triggers: list[ReplanTrigger], today: date) -> str:
    """The synthesized coaching instruction handed to the LLM for an auto re-plan."""
    reasons = "; ".join(t.reason for t in triggers)
    return (
        "Automatically re-plan the remaining weeks of this program. "
        f"Reason(s): {reasons}. "
        f"Preserve the training already completed, rebuild the schedule from today "
        f"({today.isoformat()}) forward, and keep periodizing toward the active "
        "objective so the athlete still peaks on time. If the plan has run out of "
        "scheduled workouts, extend it appropriately toward the objective."
    )
