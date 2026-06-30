"""Deriving the *focus* objective from a user's set of objectives.

A user may hold several objectives at once (multiple dated peaks + an open-ended
"general health" goal). The coach periodizes toward exactly one at a time — the
*focus*. The rule, in priority order:

1. **Manual override** — if an objective is ``is_primary``, it is the focus
   (the partial unique index guarantees at most one).
2. **Next peak** — otherwise the soonest *upcoming* dated objective
   (``target_date >= today``); ties broken by higher ``priority`` then lower id
   (earlier-created).
3. **Standing goal** — otherwise the highest-``priority`` open-ended objective
   (general health / maintenance), most-recent first.
4. **None** — no objective drives generation (coach falls back to generic
   routine-driven behavior).

The derivation (``pick_focus`` / ``dated_timeline``) is a pure function over ORM
rows so it is unit-testable without a database, mirroring the materializer.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.identity import Identity
from api.db.models import Objective


def effective_end(o: Objective) -> date | None:
    """The day an objective stops being 'upcoming' — its event's last day for a
    multi-day event, else its peak/target day."""
    return o.event_end_date or o.target_date


def is_sub_objective(o: Objective) -> bool:
    """A sub-objective (training milestone) is one nested under a parent. It is
    never a focus-eligible peak of its own — it lives inside the parent's block."""
    return o.parent_objective_id is not None


def top_level(objectives: Sequence[Objective]) -> list[Objective]:
    """Only the standalone objectives — sub-objectives (milestones) are excluded
    from focus/timeline derivation so they can't hijack the focus from their
    parent (the crux of the sub-objective design)."""
    return [o for o in objectives if not is_sub_objective(o)]


def pick_focus(objectives: Sequence[Objective], today: date) -> Objective | None:
    """Derive the focus objective from a user's objectives (pure).

    Sub-objectives are excluded up front: a milestone nested under a parent
    (e.g. "Mailbox Peak" under "Climb Baker") must never become the focus on its
    own date — it is part of the parent's plan, not a competing peak."""
    candidates = top_level(objectives)

    # 1. Manual override pin wins outright.
    for o in candidates:
        if o.is_primary:
            return o

    # 2. Soonest dated peak whose event hasn't finished (still the focus while you
    #    are ON a multi-day event).
    upcoming = [
        o
        for o in candidates
        if o.kind == "dated"
        and o.target_date is not None
        and effective_end(o) >= today
    ]
    if upcoming:
        upcoming.sort(
            key=lambda o: (o.target_date, -(o.priority or 0), o.id or 0)
        )
        return upcoming[0]

    # 3. Standing open-ended goal (general health / maintenance).
    standing = [o for o in candidates if o.kind == "open_ended"]
    if standing:
        standing.sort(key=lambda o: (-(o.priority or 0), -(o.id or 0)))
        return standing[0]

    # 4. Nothing drives generation.
    return None


def dated_timeline(objectives: Sequence[Objective]) -> list[Objective]:
    """All top-level dated objectives in chronological order (pure) — the peak
    timeline. Sub-objectives are excluded (they're surfaced nested under their
    parent via ``milestones_for``, not as standalone peaks)."""
    dated = [
        o
        for o in top_level(objectives)
        if o.kind == "dated" and o.target_date is not None
    ]
    dated.sort(key=lambda o: (o.target_date, -(o.priority or 0), o.id or 0))
    return dated


def milestones_for(
    objectives: Sequence[Objective], parent_id: int | None
) -> list[Objective]:
    """The sub-objectives (training milestones) of ``parent_id``, chronologically.

    Empty for ``None`` or a parent with no milestones. Pure over the full object
    set so the coach + API derive a parent's benchmarks without an extra query."""
    if parent_id is None:
        return []
    subs = [o for o in objectives if o.parent_objective_id == parent_id]
    subs.sort(key=lambda o: (o.target_date or date.max, -(o.priority or 0), o.id or 0))
    return subs


def load_objectives(db: Session, ident: Identity) -> list[Objective]:
    """All of a user's objectives (unordered query; callers derive ordering)."""
    return list(
        db.scalars(
            select(Objective).where(
                Objective.tenant_id == ident.tenant_id,
                Objective.user_id == ident.user_id,
            )
        ).all()
    )


def resolve_focus_objective(
    db: Session, ident: Identity, today: date | None = None
) -> Objective | None:
    """DB-backed focus resolution — the single chokepoint every consumer uses."""
    if today is None:
        today = date.today()
    return pick_focus(load_objectives(db, ident), today)
