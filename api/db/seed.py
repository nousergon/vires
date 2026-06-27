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

from api.db.fts import build_keywords, fts_sync_exercise, fts_upsert
from api.db.identity import ensure_dev_identity
from api.db.models import Exercise, ExerciseAlias
from api.db.session import SessionLocal

SEED_PATH = pathlib.Path(__file__).resolve().parent / "seed_data" / "exercises.json"

# Curated gym abbreviations / common names -> canonical catalog entry. Applied
# only when the target exists. These ride the FTS keywords so BM25 resolves
# "RDL", "OHP", "pull up" to the right exercise (free-exercise-db has no
# abbreviations of its own). The alias *mechanism* (also exposed via the API)
# is the durable piece; this is a high-confidence starter set.
ALIAS_SEED: dict[str, list[str]] = {
    "Romanian Deadlift": ["RDL"],
    "Barbell Squat": ["back squat"],
    "Barbell Full Squat": ["squat"],
    "Standing Military Press": ["OHP", "overhead press", "military press"],
    "Pullups": ["pull up", "pull-up", "pullup"],
    "Chin-Up": ["chin up", "chinup"],
    "Wide-Grip Lat Pulldown": ["lat pulldown", "pulldown"],
    "Dumbbell Bench Press": ["db bench press"],
    "Barbell Bench Press - Medium Grip": ["bench press", "flat bench press", "bb bench"],
    "Barbell Curl": ["bicep curl", "biceps curl"],
    "Standing Barbell Calf Raise": ["calf raise"],
}


def apply_alias_seed(session: Session) -> int:
    added = 0
    for target_name, aliases in ALIAS_SEED.items():
        ex = session.scalar(
            select(Exercise).where(Exercise.canonical_name == normalize_name(target_name))
        )
        if ex is None:
            continue
        existing = {a.alias_text.lower() for a in ex.aliases}
        for alias in aliases:
            if alias.lower() in existing:
                continue
            ex.aliases.append(ExerciseAlias(alias_text=alias))  # keeps collection fresh
            added += 1
        session.flush()
        fts_sync_exercise(session, ex)  # fold aliases into BM25 keywords
    session.commit()
    return added


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _load_seed() -> list[dict]:
    return json.loads(SEED_PATH.read_text())


def backfill_is_timed(session: Session) -> int:
    """Sync is_timed on canonical exercises from the seed's force=='static' flag.
    Runs even when the catalog is already seeded so the flag lands without --reset."""
    want = {
        normalize_name(r["name"]): (r.get("force") == "static")
        for r in _load_seed()
        if r.get("name")
    }
    n = 0
    for ex in session.scalars(select(Exercise).where(Exercise.provenance == "canonical")):
        target = want.get(ex.canonical_name)
        if target is not None and ex.is_timed != target:
            ex.is_timed = target
            n += 1
    session.commit()
    return n


def seed(session: Session, reset: bool = False) -> int:
    ensure_dev_identity(session)

    existing = session.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.provenance == "canonical")
    )
    if existing and not reset:
        n_timed = backfill_is_timed(session)  # keep is_timed in sync without a full reseed
        print(
            f"Catalog already has {existing} canonical exercises; skipping "
            f"(use --reset). Backfilled is_timed on {n_timed}."
        )
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
            is_timed=rec.get("force") == "static",  # isometric holds -> timed
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
    n_aliases = apply_alias_seed(session)
    print(f"Seeded {count} canonical exercises (+{n_aliases} curated aliases).")
    return count


def main() -> None:
    reset = "--reset" in sys.argv
    with SessionLocal() as session:
        seed(session, reset=reset)


if __name__ == "__main__":
    main()
