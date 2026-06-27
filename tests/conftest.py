"""Shared test fixtures.

A throwaway temp SQLite DB + npz vector store, wired in BEFORE any ``api.*``
import so the cached settings + engine bind to it. The canonical catalog is
seeded once per session; per-test fixtures clean the user-data tables so tests
stay isolated without re-seeding 800+ rows each time.
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="vires-test-")
os.environ["VIRES_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["VIRES_VECTOR_STORE_PATH"] = f"{_TMP}/test.npz"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.db.base import Base  # noqa: E402
from api.db.fts import FTS_DDL  # noqa: E402
from api.db.identity import ensure_dev_identity  # noqa: E402
from api.db.seed import seed  # noqa: E402
from api.db.session import SessionLocal, engine  # noqa: E402

# Tables holding user data (cleaned between tests); the canonical catalog stays.
_USER_TABLES = [
    "set_entries",
    "session_exercises",
    "workout_sessions",
    "template_exercises",
    "workout_templates",
    "program_slots",
    "program_weeks",
    "programs",
    "user_settings",
]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))
    with SessionLocal() as s:
        ensure_dev_identity(s)
        seed(s)
        from api.services.search import get_search_service

        get_search_service().reindex(s)
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        # remove provisional/user exercises created during the test + their FTS
        # rows + their vectors, so each test sees the pristine canonical catalog
        session.rollback()
        from api.services.search import get_search_service

        svc = get_search_service()
        rows = session.execute(
            text("SELECT id FROM exercises WHERE provenance != 'canonical'")
        ).fetchall()
        for (rid,) in rows:
            session.execute(text("DELETE FROM exercises_fts WHERE rowid = :r"), {"r": rid})
            svc.remove_exercise(rid)
        session.execute(text("DELETE FROM exercises WHERE provenance != 'canonical'"))
        for table in _USER_TABLES:
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
        session.close()


@pytest.fixture()
def client(db):
    from api.db.session import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
