"""Proves the planned_workout_reschedule_provenance migration's up/down
behavior — inspection alone can't verify a real Alembic run.

Runs Alembic in a SUBPROCESS against its own throwaway sqlite file, not
in-process: ``api.config.get_settings()`` is ``@lru_cache``d and already
bound to conftest.py's shared session-scoped test DB by the time this module
imports, and that DB's schema comes from ``Base.metadata.create_all`` (not
real Alembic migrations) — so an in-process ``alembic upgrade`` here would
collide with tables that already exist. A subprocess gets a fresh env var
and a fresh cache, exactly like a real deploy running ``alembic upgrade
head`` (mirrors tests/test_ruck_merge_migration.py).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_PRE_RESCHEDULE_REVISION = "a7ad5d99b363"


def _run_alembic(*args: str, db_path: Path) -> None:
    env = {**os.environ, "VIRES_DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stdout}\n{result.stderr}"


def _seed_planned_workout(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO tenants (id, name, created_at) VALUES ('t1','Test','2026-06-01 12:00:00')"
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, created_at) "
            "VALUES ('u1','t1','a@b.com','2026-06-01 12:00:00')"
        )
        cur.execute(
            """
            INSERT INTO planned_workouts
                (tenant_id, user_id, scheduled_date, name, status, created_by, created_at)
            VALUES
                ('t1', 'u1', '2026-07-02', 'Upper Body', 'planned', 'coach',
                 '2026-06-01 12:00:00')
            """
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def test_upgrade_adds_nullable_rescheduled_from_column():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        _run_alembic("upgrade", _PRE_RESCHEDULE_REVISION, db_path=db_path)
        pw_id = _seed_planned_workout(db_path)

        _run_alembic("upgrade", "head", db_path=db_path)

        con = sqlite3.connect(db_path)
        try:
            cols = [r[1] for r in con.execute("PRAGMA table_info(planned_workouts)")]
            assert "rescheduled_from" in cols

            row = con.execute(
                "SELECT rescheduled_from FROM planned_workouts WHERE id = ?", (pw_id,)
            ).fetchone()
            assert row == (None,)  # pre-existing row: never rescheduled
        finally:
            con.close()


def test_downgrade_drops_column_without_disturbing_others():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        _run_alembic("upgrade", _PRE_RESCHEDULE_REVISION, db_path=db_path)
        pw_id = _seed_planned_workout(db_path)
        _run_alembic("upgrade", "head", db_path=db_path)

        con = sqlite3.connect(db_path)
        try:
            con.execute(
                "UPDATE planned_workouts SET rescheduled_from = '2026-07-01' WHERE id = ?",
                (pw_id,),
            )
            con.commit()
        finally:
            con.close()

        _run_alembic("downgrade", _PRE_RESCHEDULE_REVISION, db_path=db_path)

        con = sqlite3.connect(db_path)
        try:
            cols = [r[1] for r in con.execute("PRAGMA table_info(planned_workouts)")]
            assert "rescheduled_from" not in cols

            row = con.execute(
                "SELECT scheduled_date, name, status FROM planned_workouts WHERE id = ?",
                (pw_id,),
            ).fetchone()
            assert row == ("2026-07-02", "Upper Body", "planned")
        finally:
            con.close()
