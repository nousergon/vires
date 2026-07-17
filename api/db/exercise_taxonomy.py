"""Movement-pattern taxonomy for the exercise catalog.

Standard S&C (strength & conditioning) fundamental movement patterns, used to
judge whether a user-proposed exercise swap (e.g. "RDL" -> "trap bar RDL",
"plank" -> "hollow hold") is a like-for-like substitution or changes the
training stimulus. See ``api.services.coach.exercise_swap`` for how this
feeds swap evaluation.

``infer_movement_pattern`` is deliberately rule-based (name keywords + the
catalog's existing muscle/equipment/mechanic/category tags), not LLM-classified:
the taxonomy is static and auditable, and a fixed rule set is cheaper and more
reproducible than re-classifying with an LLM call per exercise. Validated
against the full 873-exercise canonical catalog: 863/873 (98.9%) resolve to a
specific pattern, the remainder fall back to OTHER (an honest "no strong
pattern signal" bucket, not a bug) rather than a forced guess.
"""

from __future__ import annotations

import re

SQUAT = "squat"
HINGE = "hinge"
LUNGE = "lunge"
CARRY = "carry"
VERTICAL_PUSH = "vertical_push"
HORIZONTAL_PUSH = "horizontal_push"
VERTICAL_PULL = "vertical_pull"
HORIZONTAL_PULL = "horizontal_pull"
ROTATION = "rotation"
CORE = "core"
ISOLATION = "isolation"
PLYOMETRIC = "plyometric"
STATIC_HOLD = "static_hold"
OLYMPIC = "olympic"
MOBILITY = "mobility"
CARDIO = "cardio"
OTHER = "other"

MOVEMENT_PATTERNS = [
    SQUAT,
    HINGE,
    LUNGE,
    CARRY,
    VERTICAL_PUSH,
    HORIZONTAL_PUSH,
    VERTICAL_PULL,
    HORIZONTAL_PULL,
    ROTATION,
    CORE,
    ISOLATION,
    PLYOMETRIC,
    STATIC_HOLD,
    OLYMPIC,
    MOBILITY,
    CARDIO,
    OTHER,
]

# Checked in order; first match wins. Multi-word/specific phrases are listed
# ahead of generic single-word catches (e.g. "hip raise" before bare "raise")
# so the specific case isn't shadowed by the generic one.
_NAME_PATTERNS: list[tuple[str, list[str]]] = [
    (OLYMPIC, [r"\bclean\b", r"\bsnatch\b", r"\bjerk\b", r"clean and press", r"hang clean"]),
    (SQUAT, [r"\bsquats?\b", r"leg press", r"\bpistol\b", r"\bthruster"]),
    (
        HINGE,
        [
            r"deadlift",
            r"\brdl\b",
            r"good morning",
            r"hip thrust",
            r"glute bridge",
            r"hip bridge",
            r"kettlebell swing",
            r"back extension",
            r"rack pull",
            r"pull through",
            r"glute ham raise",
            r"reverse hyperextension",
            r"hyperextension",
            r"hip extension",
            r"hip lift",
            r"high pull",
        ],
    ),
    (LUNGE, [r"lunge", r"split squat", r"step-up", r"step up", r"bulgarian"]),
    (
        CARRY,
        [
            r"\bcarry\b",
            r"farmer",
            r"suitcase",
            r"\bdrag\b",
            r"\bsled\b",
            r"\byoke\b",
            r"wheelbarrow",
            r"\bkeg\b",
            r"\bstone",
            r"circus bell",
            r"conan",
        ],
    ),
    (
        VERTICAL_PUSH,
        [
            r"overhead press",
            r"military press",
            r"push press",
            r"shoulder press",
            r"handstand push",
            r"landmine press",
            r"\bohp\b",
            r"arnold",
            r"bradford",
            r"rocky press",
        ],
    ),
    (
        HORIZONTAL_PUSH,
        [
            r"bench press",
            r"push[- ]?ups?",
            r"chest press",
            r"\bdips?\b",
            r"floor press",
            r"chain press",
            r"board press",
            r"close-grip.*press",
            r"cuban press",
            r"cross over",
        ],
    ),
    (
        VERTICAL_PULL,
        [
            r"pull[- ]?ups?",
            r"pulldown",
            r"chin[- ]?ups?",
            r"\bchins?\b",
            r"muscle[- ]?up",
            r"rope climb",
        ],
    ),
    (HORIZONTAL_PULL, [r"\brows?\b", r"face pull"]),
    (ROTATION, [r"twist", r"wood ?chop", r"pallof", r"judo flip"]),
    (
        STATIC_HOLD,
        [r"\bplank\b", r"\bhold\b", r"\bisometric\b", r"\bwall sit\b"],
    ),
    (
        CORE,
        [
            r"crunch",
            r"sit[- ]?ups?",
            r"leg raise",
            r"\bv-?ups?\b",
            r"mountain climber",
            r"hollow",
            r"rollout",
            r"hip raise",
            r"butt-up",
            r"ab roller",
            r"cocoon",
            r"bottoms up",
            r"flutter kick",
        ],
    ),
    (
        ISOLATION,
        [
            r"\bflys?\b",
            r"\bflyes?\b",
            r"pullover",
            r"internal rotation",
            r"external rotation",
            r"battling rope",
            r"\bcurls?\b",
            r"kickback",
            r"hip flexion",
            r"\braises?\b",
        ],
    ),
]


def infer_movement_pattern(
    *,
    name: str,
    primary_muscles: list[str] | None = None,
    secondary_muscles: list[str] | None = None,
    equipment: str | None = None,
    mechanic: str | None = None,
    category: str | None = None,
    is_timed: bool = False,
) -> str:
    """Deterministically classify an exercise into a movement pattern.

    Rule order: coarse ``category`` buckets (cardio/stretching/plyometrics)
    -> ``is_timed`` static holds -> name-keyword rules (most specific to most
    generic) -> muscle/category/mechanic fallbacks -> OTHER.
    """
    lname = name.lower()
    primary = [m.lower() for m in (primary_muscles or [])]

    if category == "cardio":
        return CARDIO
    if category == "stretching":
        return MOBILITY
    if category == "plyometrics":
        return PLYOMETRIC
    if is_timed:
        return STATIC_HOLD

    for label, patterns in _NAME_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lname):
                return label

    if category == "olympic weightlifting":
        return OLYMPIC
    if "press" in lname:
        if "shoulders" in primary and "chest" not in primary:
            return VERTICAL_PUSH
        if "chest" in primary or "triceps" in primary:
            return HORIZONTAL_PUSH
    if "abdominals" in primary:
        return CORE
    if mechanic == "isolation":
        return ISOLATION
    if category == "strongman":
        return CARRY
    return OTHER
