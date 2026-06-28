"""Authored sport needs-analyses + constraint directive templates (coach DATA).

The objective-driven coach is credible (not generic) because it consumes a real
*needs analysis* — which qualities the objective demands and which exercise
patterns transfer. That analysis is stored as DATA on the objective
(``Objective.demands_profile``) and fed to the model via the grounding context,
rather than baked into the (public, framework-only) system prompt. Keeping the
sport-specific edge as data is what lets the public AGPL baseline stay generic
while the specific profile travels with the user's objective.

Only ``alpine`` is authored for P0 (the build spec fences additional sports out
of scope). ``defer_to_professional`` injury directives are likewise authored
here so the seed and any future UI share one source of truth.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Alpine (alpinism / mountaineering) needs-analysis
# --------------------------------------------------------------------------- #
# The dominant demands of a loaded alpine summit: hours of repeated submaximal
# effort (strength-ENDURANCE) over a max-strength base, eccentric/descent
# durability under pack load, load carriage, trunk anti-rotation/anti-lateral-
# flexion for pack + slip control, grip/calf/ankle endurance — and a taper that
# arrives FRESH on the summit date.
ALPINE_DEMANDS_PROFILE: dict[str, Any] = {
    "sport": "alpine",
    "summary": (
        "Loaded alpine objective: hours of repeated submaximal effort with a "
        "heavy pack, big eccentric/descent load, and steep load carriage. Build "
        "a max-strength base, then convert toward strength-endurance, then taper "
        "fresh to the summit date."
    ),
    "periodization": [
        "base — general strength + work capacity, moderate loads",
        "max strength — heavier loads, lower reps, on the key lower/posterior lifts",
        "muscular-endurance conversion — submaximal loads, higher reps / longer "
        "loaded carries (the alpine-specific quality)",
        "taper — shed accumulated fatigue so you arrive fresh on the summit date",
    ],
    "bias": (
        "Bias strength-ENDURANCE over max strength overall (alpinism repeats "
        "submaximal efforts for hours), built on a max-strength base block first."
    ),
    "exercise_emphasis": [
        "loaded step-ups / high box step-ups (toward real pack weight; scale to "
        "heavy carry days)",
        "eccentric / downhill quad durability (step-downs, eccentric-emphasis) — "
        "descent under load is the dominant demand and injury vector",
        "posterior chain (RDL, hip thrust, back extension) for load carriage and "
        "steep terrain",
        "loaded carries (farmer's, suitcase) — suitcase doubles as trunk "
        "anti-lateral-flexion",
        "trunk anti-rotation / anti-lateral-flexion (Pallof, suitcase) for pack "
        "carriage and slip control",
        "grip / forearm endurance, pulling, hangs",
        "calf / ankle / foot work (front-pointing on crampons)",
    ],
    "de_emphasize": [
        "bench press and aesthetic hypertrophy that does not transfer to the "
        "objective",
    ],
    "taper": "Arrive fresh on the summit date — the final week(s) shed fatigue.",
    # Catalog search terms used to assemble the candidate exercise pool the coach
    # AUTHORS routines from — the movements this objective actually demands.
    "search_terms": [
        "step up",
        "step down",
        "bulgarian split squat",
        "goblet squat",
        "romanian deadlift",
        "hip thrust",
        "back extension",
        "farmers walk",
        "suitcase carry",
        "pallof press",
        "calf raise",
        "hanging leg raise",
        "pull up",
        "plank",
        "lunge",
    ],
}


# --------------------------------------------------------------------------- #
# Constraint directive templates
# --------------------------------------------------------------------------- #
# Lumbar disc (e.g. recovering L4-L5): exclude heavy axial spinal loading; bias
# toward the deep-stabilizer / anti-rotation / anti-lateral-flexion + controlled
# eccentric work (which doubles as alpine descent durability). NEVER prescribe
# loading/rehab to TREAT the disc — defer that to the user's PT/physician.
LUMBAR_DISC_DIRECTIVES = (
    "EXCLUDE heavy axial spinal loading patterns that aggravate a lumbar disc "
    "(e.g. heavy back squat, standing overhead press, conventional deadlift to "
    "fatigue). BIAS toward deep-stabilizer, anti-rotation and anti-lateral-"
    "flexion trunk work (Pallof, suitcase carry) and controlled eccentric / "
    "descent-control work (this doubles as the alpine descent-durability work). "
    "NEVER prescribe loading or exercises to treat or rehab the disc — surface "
    "'confirm with your PT/physician' where relevant and defer the rehab itself."
)


SPORT_PROFILES: dict[str, dict[str, Any]] = {
    "alpine": ALPINE_DEMANDS_PROFILE,
}


def demands_profile_for_sport(sport: str | None) -> dict[str, Any] | None:
    """The authored needs-analysis for ``sport``, or None if no profile exists."""
    if not sport:
        return None
    return SPORT_PROFILES.get(sport.strip().lower())
