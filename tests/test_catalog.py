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
