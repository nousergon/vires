"""Proves the merge_ruck_into_activity migration's backfill SQL is correct —
inspection alone can't verify a data-migrating step like this one.

Runs Alembic in a SUBPROCESS against its own throwaway sqlite file, not
in-process: ``api.config.get_settings()`` is ``@lru_cache``d and already bound
to conftest.py's shared session-scoped test DB by the time this module
imports, and that DB's schema comes from ``Base.metadata.create_all`` (not
real Alembic migrations) — so an in-process ``alembic upgrade`` here would
collide with tables that already exist. A subprocess gets a fresh env var and
a fresh cache, exactly like a real deploy running ``alembic upgrade head``.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_PRE_MERGE_REVISION = "c3d4e5f6a7b8"


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


def _seed_ruck_row(db_path: Path) -> int:
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
            "INSERT INTO workout_sessions "
            "(tenant_id, user_id, name, session_type, started_at, ended_at) "
            "VALUES ('t1','u1','Ruck','ruck','2026-06-01 12:00:00','2026-06-01 12:00:00')"
        )
        session_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO ruck_details
                (session_id, pack_weight_kg, bodyweight_kg, distance_m,
                 elevation_gain_m, duration_s, terrain, metabolic_cost_kj,
                 source, created_at)
            VALUES (?, 20.0, 80.0, 8000.0, 300.0, 5400, 'trail', 2500.0,
                    'manual', '2026-06-01 12:00:00')
            """,
            (session_id,),
        )
        con.commit()
        return session_id
    finally:
        con.close()


def test_upgrade_backfills_ruck_details_into_activity_details():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        _run_alembic("upgrade", _PRE_MERGE_REVISION, db_path=db_path)
        session_id = _seed_ruck_row(db_path)

        _run_alembic("upgrade", "head", db_path=db_path)

        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            session_type = cur.execute(
                "SELECT session_type FROM workout_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            assert session_type == ("activity",)

            row = cur.execute(
                """
                SELECT template_key, regions, intensity, pack_weight_kg,
                       bodyweight_kg, distance_m, elevation_gain_m, terrain,
                       metabolic_cost_kj, source
                FROM activity_details WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            assert row == (
                "hike", "legs", "moderate", 20.0, 80.0, 8000.0, 300.0, "trail", 2500.0, "manual"
            )

            table_exists = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ruck_details'"
            ).fetchone()
            assert table_exists is None
        finally:
            con.close()


def test_downgrade_reconstructs_ruck_details():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        _run_alembic("upgrade", _PRE_MERGE_REVISION, db_path=db_path)
        session_id = _seed_ruck_row(db_path)
        _run_alembic("upgrade", "head", db_path=db_path)

        _run_alembic("downgrade", _PRE_MERGE_REVISION, db_path=db_path)

        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            session_type = cur.execute(
                "SELECT session_type FROM workout_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            assert session_type == ("ruck",)

            ruck = cur.execute(
                "SELECT pack_weight_kg, bodyweight_kg, distance_m, metabolic_cost_kj "
                "FROM ruck_details WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            assert ruck == (20.0, 80.0, 8000.0, 2500.0)

            cols = {r[1] for r in cur.execute("PRAGMA table_info(activity_details)")}
            assert "pack_weight_kg" not in cols
        finally:
            con.close()
