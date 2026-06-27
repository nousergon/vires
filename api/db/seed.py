"""Seed the exercise catalog from the vendored free-exercise-db slice.

    uv run python -m api.db.seed            # seed if empty
    uv run python -m api.db.seed --reset    # wipe canonical catalog + reseed

Seeded entries are ``provenance='canonical'`` and global (``tenant_id IS NULL``).
Vectors are NOT built here — run ``api.services.search.reindex`` after seeding
(kept separate so the catalog and the embedding index can be rebuilt
independently).
"""

from __future__ import annotations

import json
import pathlib
import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from api.db.fts import build_keywords, fts_upsert
from api.db.identity import ensure_dev_identity
from api.db.models import Exercise
from api.db.session import SessionLocal

SEED_PATH = pathlib.Path(__file__).resolve().parent / "seed_data" / "exercises.json"


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _load_seed() -> list[dict]:
    return json.loads(SEED_PATH.read_text())


def seed(session: Session, reset: bool = False) -> int:
    ensure_dev_identity(session)

    existing = session.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.provenance == "canonical")
    )
    if existing and not reset:
        print(f"Catalog already has {existing} canonical exercises; skipping (use --reset).")
        return 0
    if reset:
        session.execute(text("DELETE FROM exercises_fts"))
        session.query(Exercise).filter(Exercise.provenance == "canonical").delete()
        session.commit()

    records = _load_seed()
    count = 0
    for rec in records:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        instructions = rec.get("instructions") or []
        ex = Exercise(
            tenant_id=None,
            name=name,
            canonical_name=normalize_name(name),
            primary_muscles=rec.get("primaryMuscles") or [],
            secondary_muscles=rec.get("secondaryMuscles") or [],
            equipment=rec.get("equipment"),
            mechanic=rec.get("mechanic"),
            category=rec.get("category"),
            description="\n".join(instructions) if instructions else None,
            provenance="canonical",
        )
        session.add(ex)
        session.flush()  # assign ex.id for the FTS rowid
        keywords = build_keywords(
            aliases=[],
            primary_muscles=ex.primary_muscles,
            secondary_muscles=ex.secondary_muscles,
            equipment=ex.equipment,
            category=ex.category,
            mechanic=ex.mechanic,
        )
        fts_upsert(session, ex.id, ex.name, keywords)
        count += 1

    session.commit()
    print(f"Seeded {count} canonical exercises.")
    return count


def main() -> None:
    reset = "--reset" in sys.argv
    with SessionLocal() as session:
        seed(session, reset=reset)


if __name__ == "__main__":
    main()
