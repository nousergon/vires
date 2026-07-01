"""Guards the migration chain shape — catches what broke every deploy for
~2 hours on 2026-07-01 (vires-ops#39): two independently-authored revisions
(ruck_sessions, calendar_events) were scaffolded off the same parent with a
copy-pasted placeholder revision id, producing two heads. `alembic upgrade
head` then refuses to run ("Multiple head revisions are present"), and
deploy-on-merge.sh's `alembic upgrade head || exit 1` runs before the service
restart, so every deploy failed before ever touching the running process.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_single_migration_head():
    heads = _script_dir().get_heads()
    assert len(heads) == 1, (
        f"alembic has {len(heads)} heads {heads!r} — two revisions share a "
        "down_revision (or a revision id collides with another). Every "
        "revision id must be unique and the chain must resolve to exactly "
        "one head; `alembic merge heads` (or hand-editing one revision's "
        "id + down_revision, as done for vires-ops#39) fixes a split."
    )


def test_no_duplicate_revision_ids():
    revisions = list(_script_dir().walk_revisions())
    ids = [r.revision for r in revisions]
    dupes = {r for r in ids if ids.count(r) > 1}
    assert not dupes, f"duplicate alembic revision id(s): {dupes!r}"
