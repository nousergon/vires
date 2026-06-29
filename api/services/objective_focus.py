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


def pick_focus(objectives: Sequence[Objective], today: date) -> Objective | None:
    """Derive the focus objective from a user's objectives (pure)."""
    # 1. Manual override pin wins outright.
    for o in objectives:
        if o.is_primary:
            return o

    # 2. Soonest upcoming dated peak.
    upcoming = [
        o
        for o in objectives
        if o.kind == "dated" and o.target_date is not None and o.target_date >= today
    ]
    if upcoming:
        upcoming.sort(
            key=lambda o: (o.target_date, -(o.priority or 0), o.id or 0)
        )
        return upcoming[0]

    # 3. Standing open-ended goal (general health / maintenance).
    standing = [o for o in objectives if o.kind == "open_ended"]
    if standing:
        standing.sort(key=lambda o: (-(o.priority or 0), -(o.id or 0)))
        return standing[0]

    # 4. Nothing drives generation.
    return None


def dated_timeline(objectives: Sequence[Objective]) -> list[Objective]:
    """All dated objectives in chronological order (pure) — the peak timeline."""
    dated = [o for o in objectives if o.kind == "dated" and o.target_date is not None]
    dated.sort(key=lambda o: (o.target_date, -(o.priority or 0), o.id or 0))
    return dated


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
