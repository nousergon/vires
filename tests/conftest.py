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
os.environ["VIRES_NAME_VECTOR_STORE_PATH"] = f"{_TMP}/test_names.npz"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.db.base import Base  # noqa: E402
from api.db.fts import FTS_DDL  # noqa: E402
from api.db.identity import ensure_dev_identity  # noqa: E402
from api.db.seed import seed  # noqa: E402
from api.db.session import SessionLocal, engine  # noqa: E402

# Tables holding user data (cleaned between tests); the canonical catalog stays.
# Ordered children-before-parents for FK-on deletion. workout_sessions and
# planned_workouts reference each other (circular FK) — both link columns are
# nulled before the loop (see the db fixture) so neither delete is blocked.
_USER_TABLES = [
    "set_entries",
    "session_exercises",
    "planned_exercises",
    "planned_workouts",
    "workout_sessions",
    "template_exercises",
    "workout_templates",
    "programs",
    "objectives",
    "training_constraints",
    "ailment_check_ins",
    "ailment_episodes",
    "push_subscriptions",
    "user_settings",
]


@pytest.fixture(autouse=True)
def _hermetic_coach_spec(monkeypatch):
    """Pin the coach ModelSpec via the env override so tests never read the
    live /vires/llm/coach SSM parameter (the env layer wins before any boto3
    call in krepis resolve_model_spec). Names the router-edge provider
    ("litellm_proxy") — the only provider api.services.coach.agent's
    _reject_non_router_override accepts from an override since the
    2026-08-29 krepis-router migration (direct anthropic/openrouter specs are
    refused). Transport is therefore always OpenAI-compatible in tests; the
    `api.services.coach.agent._transport_client_factory` seam injects a fake
    `chat.completions`-shaped client (see tests/conftest.py's
    `install_fake_coach_client` helper) instead of monkeypatching an SDK."""
    monkeypatch.setenv("VIRES_COACH_LLM", "litellm_proxy:test-router-model")


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
        # Break the workout_sessions <-> planned_workouts FK cycle before deleting.
        session.execute(text("UPDATE workout_sessions SET planned_workout_id = NULL"))
        session.execute(text("UPDATE planned_workouts SET session_id = NULL"))
        for table in _USER_TABLES:
            session.execute(text(f"DELETE FROM {table}"))
        # Real signups (test_auth.py) create non-dev users/tenants — clean
        # those up too, but never the dev row every other test relies on.
        from api.config import get_settings

        s = get_settings()
        session.execute(text("DELETE FROM users WHERE id != :id"), {"id": s.dev_user_id})
        session.execute(text("DELETE FROM tenants WHERE id != :id"), {"id": s.dev_tenant_id})
        session.commit()
        session.close()


@pytest.fixture()
def client(db):
    from api.config import get_settings
    from api.db.identity import Identity, current_identity
    from api.db.session import get_db
    from api.main import app

    settings = get_settings()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_identity] = lambda: Identity(
        tenant_id=settings.dev_tenant_id, user_id=settings.dev_user_id
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def raw_client(db):
    """Like `client`, but WITHOUT the current_identity override — exercises
    the real Bearer-JWT auth flow end to end (test_auth_jwt.py).

    ``base_url="https://testserver"``: harmless holdover from when this
    fixture also exercised a `Secure` session cookie; kept as-is since no
    test depends on the scheme today.
    """
    from api.db.session import get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Coach LLM test seam — OpenAI-compatible fake transport client.
#
# Since the 2026-08-29 krepis-router migration (api/services/coach/agent.py),
# every resolvable coach ModelSpec uses the OpenAI-compatible transport (the
# router edge never resolves the anthropic transport) — so tests inject a
# `chat.completions.create`-shaped fake via
# `api.services.coach.agent._transport_client_factory`, not an
# `anthropic.Anthropic` monkeypatch. This is the one shared shape every coach
# test file (test_coach.py, test_coach_routines.py, test_objective_coach.py,
# test_replan_api.py) builds on.
class FakeChatMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeChatMessage(content)
        self.finish_reason = "stop"


class FakeChatCompletion:
    def __init__(self, content: str, model: str = "deepseek/deepseek-v4-flash") -> None:
        self.choices = [FakeChatChoice(content)]
        self.model = model
        self.usage = None
        self.id = "fake-completion"


class FakeChatCompletions:
    """Records every outbound request; returns the next canned payload (as
    the model's structured-output JSON) on each `.create()` call."""

    def __init__(self, canned: list[dict]) -> None:
        self.canned = canned
        self.calls = 0
        self.last_request: dict | None = None

    def create(self, **kwargs):
        import json as _json

        self.last_request = kwargs
        payload = self.canned[min(self.calls, len(self.canned) - 1)]
        self.calls += 1
        return FakeChatCompletion(_json.dumps(payload))


class FakeLLMClient:
    """OpenAI-SDK-shaped fake — `client.chat.completions.create(...)`, the
    only surface krepis's openai transport touches on the structured() path
    when a `client_factory` is supplied."""

    def __init__(self, canned: list[dict]) -> None:
        self.chat = _Namespace(completions=FakeChatCompletions(canned))

    @property
    def calls(self) -> int:
        return self.chat.completions.calls

    @property
    def last_request(self) -> dict | None:
        return self.chat.completions.last_request


class _Namespace:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)


def install_fake_coach_client(monkeypatch, canned: list[dict]) -> FakeLLMClient:
    """Point `api.services.coach.agent._transport_client_factory` at a fresh
    `FakeLLMClient` seeded with `canned` (a list of dicts — the structured
    payload each successive model call returns; the last entry repeats once
    exhausted, mirroring the retry-then-succeed shape most coach tests want).
    Returns the fake so callers can assert on `.calls` / `.last_request`."""
    from api.services.coach import agent

    fake = FakeLLMClient(canned)
    monkeypatch.setattr(agent, "_transport_client_factory", lambda: fake)
    return fake
