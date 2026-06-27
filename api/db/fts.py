"""SQLite FTS5 full-text index for the exercise catalog.

A standalone FTS5 table whose ``rowid`` mirrors ``exercises.id``. We populate it
explicitly from the service layer on create/seed/update (the catalog is
write-light: seeded once, then occasional user additions), which keeps the
sync logic in plain Python rather than DB triggers.

Two indexed columns:
* ``name``     — the display name (weighted highest at query time)
* ``keywords`` — aliases + muscles + equipment + category, space-joined
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

# Porter stemming + unicode tokenizer matches mnemon's FTS config.
FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS exercises_fts "
    "USING fts5(name, keywords, tokenize='porter unicode61')"
)


def build_keywords(
    aliases: Iterable[str] = (),
    primary_muscles: Iterable[str] = (),
    secondary_muscles: Iterable[str] = (),
    equipment: str | None = None,
    category: str | None = None,
    mechanic: str | None = None,
) -> str:
    """Flatten an exercise's searchable metadata into the FTS ``keywords`` blob."""
    parts: list[str] = []
    parts.extend(aliases)
    parts.extend(primary_muscles)
    parts.extend(secondary_muscles)
    for scalar in (equipment, category, mechanic):
        if scalar:
            parts.append(scalar)
    return " ".join(p for p in parts if p)


def fts_upsert(session: Session, rowid: int, name: str, keywords: str) -> None:
    """Insert or replace the FTS row for an exercise (rowid mirrors exercises.id)."""
    session.execute(text("DELETE FROM exercises_fts WHERE rowid = :rid"), {"rid": rowid})
    session.execute(
        text("INSERT INTO exercises_fts(rowid, name, keywords) VALUES (:rid, :name, :kw)"),
        {"rid": rowid, "name": name, "kw": keywords},
    )


def fts_delete(session: Session, rowid: int) -> None:
    session.execute(text("DELETE FROM exercises_fts WHERE rowid = :rid"), {"rid": rowid})


def fts_sync_exercise(session: Session, exercise) -> None:  # noqa: ANN001 (duck-typed ORM row)
    """Rebuild the FTS row for an exercise from its current fields + aliases."""
    keywords = build_keywords(
        aliases=[a.alias_text for a in exercise.aliases],
        primary_muscles=exercise.primary_muscles or [],
        secondary_muscles=exercise.secondary_muscles or [],
        equipment=exercise.equipment,
        category=exercise.category,
        mechanic=exercise.mechanic,
    )
    fts_upsert(session, exercise.id, exercise.name, keywords)
