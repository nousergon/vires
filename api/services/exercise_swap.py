"""Evaluate whether swapping one exercise for another preserves training stimulus.

Backs the "propose a routine modification" feature: a user (or the AI coach)
substitutes one exercise for another (e.g. Romanian Deadlift -> Trap Bar
Deadlift, Plank -> Hollow Body Hold) and gets an equivalence judgment before
the swap is accepted.

Deliberately rule-based rather than LLM-judged, for the same reason as
``api.db.exercise_taxonomy``: the comparison is a mechanical fact (same
movement pattern? overlapping target muscles? comparable equipment demand?),
so a deterministic, auditable check is both cheaper and more reliable than an
LLM call per swap.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from api.db.models import Exercise

EQUIVALENT = "equivalent"
COMPARABLE = "comparable"
DIFFERENT_STIMULUS = "different_stimulus"


@dataclass
class SwapEvaluation:
    from_exercise_id: int
    from_name: str
    to_exercise_id: int
    to_name: str
    verdict: str  # EQUIVALENT | COMPARABLE | DIFFERENT_STIMULUS
    same_pattern: bool
    muscle_overlap: float  # 0..1, Jaccard over primary+secondary muscles
    equipment_changed: bool
    rationale: str
    notes: list[str] = field(default_factory=list)


def _muscle_set(ex: Exercise) -> set[str]:
    return {m.lower() for m in (ex.primary_muscles or [])} | {
        m.lower() for m in (ex.secondary_muscles or [])
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def evaluate_swap(from_exercise: Exercise, to_exercise: Exercise) -> SwapEvaluation:
    """Compare two catalog exercises and judge whether ``to_exercise`` is a
    reasonable substitute for ``from_exercise``.

    Verdict bands:
    - EQUIVALENT: same movement pattern AND meaningful muscle overlap — a
      like-for-like swap (RDL <-> trap bar RDL, plank <-> hollow hold).
    - COMPARABLE: same movement pattern but low muscle overlap, OR different
      pattern with strong muscle overlap (e.g. squat <-> leg press) — usable,
      but the coach should note what shifted.
    - DIFFERENT_STIMULUS: neither pattern nor muscles line up — flag clearly,
      don't silently accept.
    """
    same_pattern = (
        from_exercise.movement_pattern is not None
        and from_exercise.movement_pattern == to_exercise.movement_pattern
    )
    overlap = _jaccard(_muscle_set(from_exercise), _muscle_set(to_exercise))
    equipment_changed = (from_exercise.equipment or None) != (to_exercise.equipment or None)

    notes: list[str] = []
    if same_pattern:
        notes.append(f"both are {from_exercise.movement_pattern} pattern")
    else:
        notes.append(
            f"movement pattern changes ({from_exercise.movement_pattern or 'unclassified'} "
            f"-> {to_exercise.movement_pattern or 'unclassified'})"
        )
    if overlap >= 0.5:
        notes.append("substantial target-muscle overlap")
    elif overlap > 0:
        notes.append("partial target-muscle overlap")
    else:
        notes.append("no shared target muscles")
    if equipment_changed:
        notes.append(
            f"equipment changes ({from_exercise.equipment or 'bodyweight'} "
            f"-> {to_exercise.equipment or 'bodyweight'})"
        )

    if same_pattern and overlap >= 0.34:
        verdict = EQUIVALENT
    elif same_pattern or overlap >= 0.5:
        verdict = COMPARABLE
    else:
        verdict = DIFFERENT_STIMULUS

    verdict_lead = {
        EQUIVALENT: "Solid equivalent",
        COMPARABLE: "Reasonable alternative, with a shift in stimulus",
        DIFFERENT_STIMULUS: "Different training stimulus",
    }[verdict]
    rationale = f"{verdict_lead} — {'; '.join(notes)}."

    return SwapEvaluation(
        from_exercise_id=from_exercise.id,
        from_name=from_exercise.name,
        to_exercise_id=to_exercise.id,
        to_name=to_exercise.name,
        verdict=verdict,
        same_pattern=same_pattern,
        muscle_overlap=round(overlap, 2),
        equipment_changed=equipment_changed,
        rationale=rationale,
        notes=notes,
    )


def detect_swaps(
    old_exercise_ids: list[int], new_exercise_ids: list[int]
) -> list[tuple[int, int]]:
    """Multiset diff: pairs each exercise removed from the routine with one
    added, up to ``min(len(removed), len(added))`` pairs. Order- and
    position-independent, so a swap is detected even if the edit also
    reordered or added/removed unrelated exercises elsewhere in the same
    routine. Any leftover removed/added beyond the matched pairs is a pure
    removal/addition, not a swap, and isn't returned here."""
    old_counts = Counter(old_exercise_ids)
    new_counts = Counter(new_exercise_ids)
    removed = list((old_counts - new_counts).elements())
    added = list((new_counts - old_counts).elements())
    # strict=False: an uneven removed/added count is a pure add or remove for
    # the leftover items, not a pairing bug — truncating to the shorter list
    # is the intended behavior (see docstring), not an oversight.
    return list(zip(removed, added, strict=False))
