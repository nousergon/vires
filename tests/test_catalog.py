from sqlalchemy import func, select, text

from api.db.models import Exercise


def test_catalog_seeded(db):
    n = db.scalar(select(func.count()).select_from(Exercise))
    assert n > 800  # free-exercise-db ships ~873


def test_fts_bm25_match(db):
    rows = db.execute(
        text(
            "SELECT rowid FROM exercises_fts WHERE exercises_fts MATCH 'squat' "
            "ORDER BY bm25(exercises_fts) LIMIT 5"
        )
    ).fetchall()
    assert len(rows) >= 3


def test_canonical_names_normalized(db):
    ex = db.scalar(select(Exercise).limit(1))
    assert ex.canonical_name == ex.canonical_name.lower().strip()


def test_movement_pattern_backfilled_on_seed(db):
    total = db.scalar(select(func.count()).select_from(Exercise))
    unclassified = db.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.movement_pattern.is_(None))
    )
    assert unclassified == 0, "every canonical exercise should get a movement_pattern"
    other = db.scalar(
        select(func.count())
        .select_from(Exercise)
        .where(Exercise.movement_pattern == "other")
    )
    # Long-tail residual (niche/idiosyncratic names the rule set doesn't
    # recognize) should stay small relative to the full catalog.
    assert other / total < 0.05


def test_movement_pattern_hinge_equivalents(db):
    names = {"romanian deadlift", "trap bar deadlift"}
    rows = db.scalars(select(Exercise).where(Exercise.canonical_name.in_(names))).all()
    assert len(rows) == 2
    assert {r.movement_pattern for r in rows} == {"hinge"}
