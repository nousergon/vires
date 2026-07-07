"""Same-day prescription gate — the *micro* half of ailment adaptation.

Deterministic and rules-first (label keywords + severity thresholds), NOT an
LLM call: this runs synchronously inside ``start_planned`` and must be cheap
and reproducible. The *macro* loop (``api.services.coach.replan``) is the
LLM-backed counterpart that proposes restructuring the whole plan; this gate
instead reacts to *today's* prescription, on the day it's about to be trained.

Two thresholds, same rules table:
- ``WARN_SEVERITY`` (>=5): a lower-body/knee episode is painful enough that the
  session should carry an explicit heads-up — attaches a ``notes`` warning to
  every affected exercise, but the workout still starts.
- ``BLOCK_SEVERITY`` (>=8): painful enough that starting is refused outright
  (409) rather than merely flagged — the athlete has to explicitly resolve
  or defer before training that region.

Two checks gate an exercise, both of which must pass: the ailment's own
free-text ``label`` must read lower-body/knee (keyword match — most episodes
are logged as "Right knee", "Left hamstring", etc.), AND the exercise's
``primary_muscles``/``secondary_muscles`` (from the canonical catalog) must
include a lower-body muscle. A "knee" label flags a leg-press exercise even
though no muscle group is literally named "knee" — the muscle-group side of
the check is what actually recognizes it as lower-body.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ailment label keywords that read as lower-body/knee for gating purposes.
# Deliberately narrow + literal (rules-first, no fuzzy matching) — false
# negatives here just mean no warning is added, not a safety hole, since the
# user still sees their own ailment list and check-in trend.
_LOWER_BODY_LABEL_KEYWORDS = (
    "knee", "leg", "quad", "hamstring", "calf", "calves", "ankle", "shin",
    "hip", "glute", "thigh", "acl", "mcl", "meniscus", "patell",
)

# Exercise primary/secondary muscle tags (canonical catalog) that count as
# lower-body for this gate.
_LOWER_BODY_MUSCLES = frozenset(
    {"quadriceps", "hamstrings", "glutes", "calves", "adductors", "abductors"}
)

# Session-level heads-up: a lower-body ailment is significant enough that
# today's affected exercises get an explicit notes warning, but training
# still proceeds.
WARN_SEVERITY = 5

# Session-level stop: painful enough that starting is refused outright rather
# than merely flagged.
BLOCK_SEVERITY = 8


@dataclass(frozen=True)
class AilmentFlag:
    label: str
    severity: int


@dataclass(frozen=True)
class ExerciseGateInput:
    """The minimal shape the gate needs for one prescribed exercise — pure, no
    ORM dependency, so it's unit-testable without a DB."""

    exercise_id: int
    muscles: frozenset[str] = field(default_factory=frozenset)


def _is_lower_body_label(label: str) -> bool:
    lowered = label.lower()
    return any(kw in lowered for kw in _LOWER_BODY_LABEL_KEYWORDS)


def _is_lower_body_exercise(muscles: frozenset[str]) -> bool:
    return not muscles.isdisjoint(_LOWER_BODY_MUSCLES)


def relevant_ailment_flags(
    ailments: list[AilmentFlag], *, min_severity: int = WARN_SEVERITY
) -> list[AilmentFlag]:
    """Open lower-body/knee ailments at or above ``min_severity`` (by label)."""
    return [
        a for a in ailments if a.severity >= min_severity and _is_lower_body_label(a.label)
    ]


def blocking_flags(ailments: list[AilmentFlag]) -> list[AilmentFlag]:
    return relevant_ailment_flags(ailments, min_severity=BLOCK_SEVERITY)


def warning_note(flags: list[AilmentFlag]) -> str | None:
    """The ``notes`` warning to prepend for a lower-body exercise, or ``None``
    if nothing qualifies. Joins every qualifying flag so a session with both a
    knee and a hip flare-up gets one combined note, not one per ailment."""
    if not flags:
        return None
    parts = "; ".join(f"{f.label} at {f.severity}/10" for f in flags)
    return f"⚠ Ailment check-in: {parts} — consider lighter load or a swap for this exercise."


def gate_exercise(
    exercise: ExerciseGateInput, flags: list[AilmentFlag]
) -> str | None:
    """The warning note for one prescribed exercise, or ``None``. An exercise is
    "affected" if the ailment's label reads lower-body/knee OR the exercise
    itself trains a lower-body muscle (either signal is enough — see module
    docstring)."""
    if not flags:
        return None
    if not _is_lower_body_exercise(exercise.muscles):
        # The ailment reads lower-body by label, but this particular exercise
        # doesn't train a lower-body muscle (e.g. bench press) — no warning.
        return None
    return warning_note(flags)
