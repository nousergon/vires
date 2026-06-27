"""ORM -> Pydantic serializers shared across routers."""

from __future__ import annotations

from api.db.models import Exercise
from api.schemas.exercise import ExerciseBrief, ExerciseOut


def to_exercise_out(ex: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=ex.id,
        name=ex.name,
        primary_muscles=ex.primary_muscles or [],
        secondary_muscles=ex.secondary_muscles or [],
        equipment=ex.equipment,
        mechanic=ex.mechanic,
        category=ex.category,
        description=ex.description,
        provenance=ex.provenance,
        aliases=[a.alias_text for a in ex.aliases],
    )


def to_exercise_brief(ex: Exercise) -> ExerciseBrief:
    return ExerciseBrief(
        id=ex.id,
        name=ex.name,
        primary_muscles=ex.primary_muscles or [],
        equipment=ex.equipment,
    )
