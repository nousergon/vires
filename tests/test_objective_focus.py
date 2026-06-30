"""Focus derivation over a user's objectives (pure, no DB).

Covers the rule in ``api.services.objective_focus.pick_focus``: manual override
> soonest upcoming dated peak > standing open-ended goal > none.
"""

from __future__ import annotations

from datetime import date

from api.db.models import Objective
from api.services.objective_focus import (
    dated_timeline,
    milestones_for,
    pick_focus,
    top_level,
)

TODAY = date(2026, 6, 29)


def _obj(
    id: int,
    *,
    kind: str = "dated",
    target_date: date | None = None,
    event_end_date: date | None = None,
    is_primary: bool = False,
    priority: int = 0,
    parent_objective_id: int | None = None,
) -> Objective:
    return Objective(
        id=id,
        name=f"o{id}",
        kind=kind,
        target_date=target_date,
        event_end_date=event_end_date,
        is_primary=is_primary,
        priority=priority,
        parent_objective_id=parent_objective_id,
    )


def test_pick_focus_none_when_empty():
    assert pick_focus([], TODAY) is None


def test_primary_override_wins_over_sooner_dated():
    pinned = _obj(1, target_date=date(2026, 12, 1), is_primary=True)
    sooner = _obj(2, target_date=date(2026, 7, 1))
    assert pick_focus([sooner, pinned], TODAY).id == 1


def test_soonest_upcoming_dated_is_focus():
    a = _obj(1, target_date=date(2026, 9, 1))
    b = _obj(2, target_date=date(2026, 7, 15))
    c = _obj(3, target_date=date(2026, 12, 1))
    assert pick_focus([a, b, c], TODAY).id == 2


def test_passed_dated_objectives_ignored():
    past = _obj(1, target_date=date(2026, 1, 1))
    assert pick_focus([past], TODAY) is None


def test_objective_stays_focus_during_multi_day_event():
    # peak day was yesterday but the trip runs through next week -> still the focus
    on_trip = _obj(
        1, target_date=date(2026, 6, 28), event_end_date=date(2026, 7, 3)
    )
    later = _obj(2, target_date=date(2026, 8, 1))
    assert pick_focus([on_trip, later], TODAY).id == 1


def test_objective_drops_after_event_end():
    over = _obj(1, target_date=date(2026, 6, 20), event_end_date=date(2026, 6, 25))
    assert pick_focus([over], TODAY) is None


def test_priority_breaks_same_date_tie():
    lo = _obj(1, target_date=date(2026, 8, 1), priority=1)
    hi = _obj(2, target_date=date(2026, 8, 1), priority=5)
    assert pick_focus([lo, hi], TODAY).id == 2


def test_today_counts_as_upcoming():
    today_obj = _obj(1, target_date=TODAY)
    assert pick_focus([today_obj], TODAY).id == 1


def test_open_ended_fallback_when_no_upcoming_dated():
    past = _obj(1, target_date=date(2026, 1, 1))
    standing = _obj(2, kind="open_ended", priority=3)
    assert pick_focus([past, standing], TODAY).id == 2


def test_upcoming_dated_beats_high_priority_open_ended():
    standing = _obj(1, kind="open_ended", priority=99)
    upcoming = _obj(2, target_date=date(2026, 7, 1))
    assert pick_focus([standing, upcoming], TODAY).id == 2


def test_dated_timeline_is_chronological_and_excludes_open_ended():
    a = _obj(1, target_date=date(2026, 9, 1))
    b = _obj(2, target_date=date(2026, 7, 1))
    c = _obj(3, kind="open_ended")
    assert [o.id for o in dated_timeline([a, b, c])] == [2, 1]


# --------------------------------------------------------------------------- #
# Sub-objectives (training milestones) — the crux: a sub-objective must NEVER
# hijack the focus from its parent, even though its own date is sooner.
# --------------------------------------------------------------------------- #
def test_sub_objective_does_not_hijack_focus_from_parent():
    # Parent peaks 7/9; the sub-objective (Mailbox Peak) is sooner at 7/5 but is
    # nested under the parent — the parent stays the focus.
    parent = _obj(1, target_date=date(2026, 7, 9))
    sub = _obj(2, target_date=date(2026, 7, 5), parent_objective_id=1)
    assert pick_focus([parent, sub], TODAY).id == 1


def test_sub_objective_excluded_from_dated_timeline():
    parent = _obj(1, target_date=date(2026, 7, 9))
    sub = _obj(2, target_date=date(2026, 7, 5), parent_objective_id=1)
    assert [o.id for o in dated_timeline([parent, sub])] == [1]


def test_sub_objective_not_focus_even_when_only_objective():
    # An orphan-ish sub (parent set but parent not in the set) is still excluded;
    # a sub-objective is never a standalone focus.
    sub = _obj(2, target_date=date(2026, 7, 5), parent_objective_id=99)
    assert pick_focus([sub], TODAY) is None


def test_top_level_filters_out_sub_objectives():
    parent = _obj(1, target_date=date(2026, 7, 9))
    sub = _obj(2, target_date=date(2026, 7, 5), parent_objective_id=1)
    standing = _obj(3, kind="open_ended")
    assert {o.id for o in top_level([parent, sub, standing])} == {1, 3}


def test_milestones_for_returns_subs_chronologically():
    parent = _obj(1, target_date=date(2026, 8, 1))
    m_late = _obj(2, target_date=date(2026, 7, 20), parent_objective_id=1)
    m_early = _obj(3, target_date=date(2026, 7, 5), parent_objective_id=1)
    other = _obj(4, target_date=date(2026, 7, 6), parent_objective_id=99)
    assert [o.id for o in milestones_for([parent, m_late, m_early, other], 1)] == [3, 2]


def test_milestones_for_none_parent_is_empty():
    assert milestones_for([_obj(1, target_date=date(2026, 8, 1))], None) == []
