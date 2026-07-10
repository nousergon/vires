"""Magic-link auth: request/verify, sessions, allowlist, tenant isolation.

Uses `raw_client` (no current_identity override — see conftest.py) so the
real cookie-based flow is exercised end to end, unlike every other test file
which authenticates via the dev-identity override.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def _capture_sent_links(monkeypatch) -> list[tuple[str, str]]:
    """Stub the Resend call and capture (email, link) instead of sending."""
    sent: list[tuple[str, str]] = []

    async def fake_send(email: str, link: str) -> None:
        sent.append((email, link))

    monkeypatch.setattr("api.routers.auth.send_magic_link", fake_send)
    return sent


def _token_from_link(link: str) -> str:
    m = re.search(r"[?&]token=([^&]+)", link)
    assert m, f"no token in link: {link}"
    return m.group(1)


def _signup(raw_client, monkeypatch, email: str) -> str:
    """Request + verify a magic link for a brand-new (already-allowed)
    email; returns the raw token (in case a test wants to replay/inspect it)."""
    sent = _capture_sent_links(monkeypatch)
    r = raw_client.post("/api/auth/magic-link", json={"email": email})
    assert r.status_code == 200, r.text
    token = _token_from_link(sent[-1][1])
    v = raw_client.post("/api/auth/magic-link/verify", json={"token": token})
    assert v.status_code == 200, v.text
    return token


def test_bootstrap_first_user_needs_no_allowlisting_and_becomes_admin(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")
    me = raw_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"email": "brian@example.com", "display_name": None, "is_admin": True}


def test_new_email_not_on_allowlist_is_rejected_after_bootstrap(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap user
    sent = _capture_sent_links(monkeypatch)
    r = raw_client.post("/api/auth/magic-link", json={"email": "friend@example.com"})
    assert r.status_code == 403
    assert sent == []  # never even sent


def test_allowlisted_email_can_sign_up_with_no_extra_field(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap -> admin
    added = raw_client.post("/api/auth/allowlist", json={"email": "friend@example.com"})
    assert added.status_code == 201, added.text
    assert added.json()["email"] == "friend@example.com"
    assert added.json()["used_at"] is None

    from api.main import app

    friend = TestClient(app, base_url="https://testserver")
    # No invite code / extra field of any kind — just the email.
    _signup(friend, monkeypatch, "friend@example.com")
    me = friend.get("/api/auth/me")
    assert me.json()["email"] == "friend@example.com"
    assert me.json()["is_admin"] is False


def test_allowlist_entry_marked_used_after_signup(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap -> admin
    raw_client.post("/api/auth/allowlist", json={"email": "friend@example.com"})

    from api.main import app

    friend = TestClient(app, base_url="https://testserver")
    _signup(friend, monkeypatch, "friend@example.com")

    listing = raw_client.get("/api/auth/allowlist").json()
    entry = next(e for e in listing if e["email"] == "friend@example.com")
    assert entry["used_at"] is not None


def test_adding_the_same_email_twice_is_idempotent(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap -> admin
    first = raw_client.post("/api/auth/allowlist", json={"email": "friend@example.com"})
    second = raw_client.post("/api/auth/allowlist", json={"email": "friend@example.com"})
    assert first.status_code == 201 and second.status_code == 201
    listing = raw_client.get("/api/auth/allowlist").json()
    assert len([e for e in listing if e["email"] == "friend@example.com"]) == 1


def test_magic_link_is_single_use(raw_client, monkeypatch):
    sent = _capture_sent_links(monkeypatch)
    raw_client.post("/api/auth/magic-link", json={"email": "brian@example.com"})
    token = _token_from_link(sent[-1][1])

    first = raw_client.post("/api/auth/magic-link/verify", json={"token": token})
    assert first.status_code == 200

    replay = TestClient(raw_client.app, base_url="https://testserver")
    r = replay.post("/api/auth/magic-link/verify", json={"token": token})
    assert r.status_code == 401


def test_expired_magic_link_is_rejected(raw_client, monkeypatch, db):
    sent = _capture_sent_links(monkeypatch)
    raw_client.post("/api/auth/magic-link", json={"email": "brian@example.com"})
    token = _token_from_link(sent[-1][1])

    from api.db.identity import hash_token
    from api.db.models import MagicLinkToken

    row = db.query(MagicLinkToken).filter_by(token_hash=hash_token(token)).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    r = raw_client.post("/api/auth/magic-link/verify", json={"token": token})
    assert r.status_code == 401


def test_garbage_token_is_rejected(raw_client):
    r = raw_client.post("/api/auth/magic-link/verify", json={"token": "not-a-real-token"})
    assert r.status_code == 401


def test_unauthenticated_request_is_401(raw_client):
    r = raw_client.get("/api/auth/me")
    assert r.status_code == 401


def test_authenticated_request_reaches_a_normal_route_via_the_session_cookie(
    raw_client, monkeypatch
):
    _signup(raw_client, monkeypatch, "brian@example.com")
    # Any ordinary route works via Depends(current_identity) unchanged.
    r = raw_client.get("/api/workouts")
    assert r.status_code == 200


def test_logout_invalidates_the_session(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")
    assert raw_client.get("/api/auth/me").status_code == 200

    out = raw_client.post("/api/auth/logout")
    assert out.status_code == 204

    assert raw_client.get("/api/auth/me").status_code == 401


def test_non_admin_cannot_manage_the_allowlist(raw_client, monkeypatch):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap admin
    raw_client.post("/api/auth/allowlist", json={"email": "friend@example.com"})

    from api.main import app

    friend = TestClient(app, base_url="https://testserver")
    _signup(friend, monkeypatch, "friend@example.com")  # not admin
    assert friend.post("/api/auth/allowlist", json={"email": "x@example.com"}).status_code == 403
    assert friend.get("/api/auth/allowlist").status_code == 403


def test_magic_link_rate_limited_after_five_requests_per_minute(raw_client, monkeypatch):
    sent = _capture_sent_links(monkeypatch)
    for _ in range(5):
        r = raw_client.post("/api/auth/magic-link", json={"email": "spammed@example.com"})
        assert r.status_code == 200
    r = raw_client.post("/api/auth/magic-link", json={"email": "spammed@example.com"})
    assert r.status_code == 429
    assert len(sent) == 5  # the 6th never sent


def test_two_signed_up_users_cannot_see_each_others_workouts(raw_client, monkeypatch):
    from api.main import app

    a = raw_client
    b = TestClient(app, base_url="https://testserver")
    _signup(a, monkeypatch, "a@example.com")  # bootstrap -> admin
    a.post("/api/auth/allowlist", json={"email": "b@example.com"})
    _signup(b, monkeypatch, "b@example.com")

    ws = a.post("/api/workouts", json={"name": "A's workout"}).json()
    assert b.get(f"/api/workouts/{ws['id']}").status_code == 404
    assert ws["id"] not in [w["id"] for w in b.get("/api/workouts").json()]


@pytest.fixture()
def _allowlist_not_required(monkeypatch):
    monkeypatch.setenv("VIRES_ALLOWLIST_REQUIRED", "false")
    from api.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_open_signup_when_allowlist_not_required(raw_client, monkeypatch, _allowlist_not_required):
    _signup(raw_client, monkeypatch, "brian@example.com")  # bootstrap
    from api.main import app

    anyone = TestClient(app, base_url="https://testserver")
    sent = _capture_sent_links(monkeypatch)
    r = anyone.post("/api/auth/magic-link", json={"email": "anyone@example.com"})
    assert r.status_code == 200
    assert len(sent) == 1
