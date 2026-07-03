"""Fixed catalog of activity templates: cross-training + locomotion.

Each entry is a starting point for the quick-log form — a label plus a coarse
``regions``/``intensity`` default the user can freely edit before saving. This
is deliberately a small hardcoded list, not a database table: the catalog is
product taste (which activities are common enough to deserve a one-tap
default), not user data, and it's cheap to extend by editing this file. A
'custom' pseudo-entry (freeform name, no default) is always available via
``ActivityLogIn.template_key = "custom"`` and isn't listed here since it has
no fixed label.

``route_capable`` templates (Walk, Run, Hike) additionally get the frontend's
route-capture UI (manual entry / trail search / draw / GPX import) plus an
optional pack-weight + bodyweight section that unlocks the Pandolf
metabolic-cost estimate — see ``api.db.models.ActivityDetail``. Every other
template is a coarse regions/intensity estimate only, same as before.

The last five entries (race / league_game / recreation_event / trip /
rehab_window) fold in what used to be the separate ``CalendarEvent.type``
enum (merge_calendar_events_into_activity) — a race is exactly as much "an
activity with a type picker" as a Walk is; the only thing that varies is
whether the frontend shows the future/recurring section (driven purely by
the chosen date, never by which template was picked — see ``ActivityForm``).
"""

from __future__ import annotations

from api.schemas.workout import ActivityTemplateOut

# (key, label, regions, intensity, route_capable). regions:
# 'legs'|'upper'|'full'|'core'|'none'; intensity: 'light'|'moderate'|'hard'
# (see api.schemas.workout).
_CATALOG: list[tuple[str, str, str, str, bool]] = [
    ("walk", "Walk", "legs", "light", True),
    ("run", "Run", "legs", "moderate", True),
    ("hike", "Hike", "legs", "moderate", True),
    ("climbing_indoor_toprope", "Indoor top-rope", "upper", "moderate", False),
    ("climbing_bouldering", "Bouldering", "upper", "hard", False),
    ("swimming", "Swimming", "full", "moderate", False),
    ("cycling", "Cycling", "legs", "moderate", False),
    ("yoga", "Yoga", "full", "light", False),
    ("tennis", "Tennis", "full", "hard", False),
    ("basketball", "Basketball", "legs", "hard", False),
    ("soccer", "Soccer", "legs", "hard", False),
    ("skiing", "Skiing / snowboarding", "legs", "hard", False),
    ("rowing", "Rowing (erg)", "full", "hard", False),
    ("martial_arts", "Martial arts", "full", "hard", False),
    ("mobility", "Mobility / stretching", "full", "light", False),
    # Folded in from the retired CalendarEvent.type enum.
    ("race", "Race / competition", "legs", "hard", False),
    ("league_game", "League game", "full", "hard", False),
    ("recreation_event", "Recreational outing", "full", "moderate", False),
    ("trip", "Trip", "full", "light", False),
    ("rehab_window", "Rehab window", "full", "light", False),
]

ACTIVITY_TEMPLATES: list[ActivityTemplateOut] = [
    ActivityTemplateOut(
        key=key, label=label, regions=regions, intensity=intensity, route_capable=route_capable
    )
    for key, label, regions, intensity, route_capable in _CATALOG
]

_BY_KEY = {t.key: t for t in ACTIVITY_TEMPLATES}


def get_activity_template(key: str) -> ActivityTemplateOut | None:
    return _BY_KEY.get(key)
