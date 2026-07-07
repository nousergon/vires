"""Macro re-plan triggers — the event-driven half of post-workout adaptation.

The *micro* loop (``autoregulate``) silently nudges loads every workout. This
*macro* loop watches for **structural** events that mean the plan's shape is
stale — missed sessions, the plan running out, the objective passing or
changing, an ailment flaring up — and, when one fires, the coach **proposes** a
re-plan the user must confirm (never silent; reuses the existing modify→PUT
cutover). See vires-ops#9, vires-ops#50.

Detection is deterministic and fed entirely by in-app data we already own.
``evaluate_triggers`` is pure (no DB) so it is unit-testable; ``detect_triggers``
is the thin DB wrapper. Generating the actual proposal (the LLM call) is left to
the router so detection stays cheap — the frontend checks first, then asks for a
proposal only when a trigger fired.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

from sqlalchemy.orm import Session

from api.db.identity import Identity
from api.db.models import Objective, Program
from api.services.coach.objective_context import AilmentEpisodeCtx
from api.services.objective_focus import effective_end, resolve_focus_objective

# Past planned-but-never-started sessions before a re-plan is suggested.
MISSED_SESSIONS_THRESHOLD = 2

# An open ailment episode is flagged once its latest check-in reaches this
# severity (0-10 scale) — painful enough that the plan itself, not just
# today's session, should be reconsidered.
AILMENT_SEVERITY_THRESHOLD = 6

# A single check-in-to-check-in jump of this many points reads as an acute
# change (a flare-up or a big improvement) worth re-planning around, even if
# the absolute level is still below AILMENT_SEVERITY_THRESHOLD.
AILMENT_SEVERITY_DELTA_THRESHOLD = 3

# A registration counts as "new" for this many days — long enough that the
# suggestion survives a same-day replan-check retry, short enough that a
# months-old episode with a thin check-in history doesn't perpetually read
# as freshly registered.
AILMENT_NEW_WINDOW_DAYS = 3


@dataclass(frozen=True)
class ReplanTrigger:
    # missed_sessions | plan_exhausted | objective_passed | objective_changed |
    # ailment_changed
    kind: str
    reason: str  # plain-English, shown to the user


def _ailment_trigger(
    ailments: Iterable[AilmentEpisodeCtx],
    *,
    severity_threshold: int,
    delta_threshold: int,
    today: date,
) -> ReplanTrigger | None:
    """An open ailment fires the macro loop when it's newly registered, has
    jumped by ``delta_threshold`` points between consecutive check-ins, or has
    reached ``severity_threshold``. Mirrors the other structural triggers:
    stateless (re-derived from current data, not a diff against "last seen"),
    so it keeps firing until the user either resolves the episode or accepts a
    re-plan — same shape as ``plan_exhausted`` persisting until the plan is
    refreshed."""
    for ep in ailments:
        if ep.status == "resolved":
            continue
        if today - ep.onset_date <= timedelta(days=AILMENT_NEW_WINDOW_DAYS):
            sev = ep.latest_severity
            sev_note = f" (severity {sev}/10)." if sev is not None else "."
            return ReplanTrigger("ailment_changed", f"New ailment logged: {ep.label}{sev_note}")
        ordered = sorted(ep.check_ins, key=lambda c: c.check_in_date)
        for prev, cur in pairwise(ordered):
            if abs(cur.severity - prev.severity) >= delta_threshold:
                return ReplanTrigger(
                    "ailment_changed",
                    f"{ep.label} severity jumped from {prev.severity} to "
                    f"{cur.severity}/10 on {cur.check_in_date.isoformat()}.",
                )
        if ep.latest_severity is not None and ep.latest_severity >= severity_threshold:
            return ReplanTrigger(
                "ailment_changed",
                f"{ep.label} is at severity {ep.latest_severity}/10 — the plan may need to adapt.",
            )
    return None


def evaluate_triggers(
    planned: Iterable,
    *,
    program_objectives: list[Objective],
    focus_objective: Objective | None,
    today: date,
    missed_threshold: int = MISSED_SESSIONS_THRESHOLD,
    ailments: Iterable[AilmentEpisodeCtx] = (),
    ailment_severity_threshold: int = AILMENT_SEVERITY_THRESHOLD,
    ailment_delta_threshold: int = AILMENT_SEVERITY_DELTA_THRESHOLD,
) -> list[ReplanTrigger]:
    """Which structural re-plan triggers have fired (pure).

    Season-aware: ``program_objectives`` is EVERY objective the program trains
    for (its season blocks), not a single one — so a passed block fires while
    later blocks remain, and a newly-added focus the season doesn't cover fires
    objective_changed.

    ``ailments`` is the user's open episodes (not program-scoped — an injury
    affects whichever plan is active), so it fires the same regardless of which
    program is being checked."""
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

    ailment_trigger = _ailment_trigger(
        ailments,
        severity_threshold=ailment_severity_threshold,
        delta_threshold=ailment_delta_threshold,
        today=today,
    )
    if ailment_trigger is not None:
        triggers.append(ailment_trigger)

    return triggers


def detect_triggers(
    db: Session, ident: Identity, program: Program, today: date | None = None
) -> list[ReplanTrigger]:
    """DB-backed trigger detection for a program."""
    # Imported here (not at module scope) to avoid a context.py <-> replan.py
    # import cycle down the line — both live under api.services.coach.
    from api.services.coach.context import build_ailment_ctxs

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
        ailments=build_ailment_ctxs(db, ident),
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
