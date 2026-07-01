"""Fixed catalog of generic cross-training activity templates.

Each entry is a starting point for the quick-log form — a label plus a coarse
``regions``/``intensity`` default the user can freely edit before saving. This
is deliberately a small hardcoded list, not a database table: the catalog is
product taste (which activities are common enough to deserve a one-tap
default), not user data, and it's cheap to extend by editing this file. A
'custom' pseudo-entry (freeform name, no default) is always available via
``ActivityLogIn.template_key = "custom"`` and isn't listed here since it has
no fixed label.
"""

from __future__ import annotations

from api.schemas.workout import ActivityTemplateOut

# (key, label, regions, intensity). regions: 'legs'|'upper'|'full'|'core'|'none';
# intensity: 'light'|'moderate'|'hard' (see api.schemas.calendar_event).
_CATALOG: list[tuple[str, str, str, str]] = [
    ("climbing_indoor_toprope", "Indoor top-rope", "upper", "moderate"),
    ("climbing_bouldering", "Bouldering", "upper", "hard"),
    ("swimming", "Swimming", "full", "moderate"),
    ("cycling", "Cycling", "legs", "moderate"),
    ("running", "Running", "legs", "moderate"),
    ("yoga", "Yoga", "full", "light"),
    ("tennis", "Tennis", "full", "hard"),
    ("basketball", "Basketball", "legs", "hard"),
    ("soccer", "Soccer", "legs", "hard"),
    ("hiking", "Hiking (unloaded)", "legs", "light"),
    ("skiing", "Skiing / snowboarding", "legs", "hard"),
    ("rowing", "Rowing (erg)", "full", "hard"),
    ("martial_arts", "Martial arts", "full", "hard"),
    ("mobility", "Mobility / stretching", "full", "light"),
]

ACTIVITY_TEMPLATES: list[ActivityTemplateOut] = [
    ActivityTemplateOut(key=key, label=label, regions=regions, intensity=intensity)
    for key, label, regions, intensity in _CATALOG
]

_BY_KEY = {t.key: t for t in ACTIVITY_TEMPLATES}


def get_activity_template(key: str) -> ActivityTemplateOut | None:
    return _BY_KEY.get(key)
