"""Shared-identity bearer-JWT path (vires-ops#60).

Uses `raw_client` (no current_identity override) so the real verification
path runs end to end. Only the JWKS **fetch** is stubbed — signature checks
(real Ed25519 keys), `exp`/`iss`/`aud` enforcement, and the resolution
ladder (identity_user_id → email link → JIT-provision) all execute for real.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

ISSUER = "https://auth.nousergon.ai"  # matches Settings.auth_base_url default

_PRIVATE_KEY = Ed25519PrivateKey.generate()
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch):
    """Serve the test keypair's public half where the JWKS lookup would go —
    everything downstream of the key fetch is the real code path."""
    import api.services.auth_jwt as auth_jwt

    stub = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=_PUBLIC_KEY)
    )
    monkeypatch.setattr(auth_jwt, "_jwk_client", lambda: stub)


def make_token(
    sub: str,
    email: str | None,
    *,
    issuer: str = ISSUER,
    audience: str = ISSUER,
    expires_in: int = 300,
    key: Ed25519PrivateKey | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict = {
        "sub": sub,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    if email is not None:
        claims["email"] = email
    return pyjwt.encode(claims, key or _PRIVATE_KEY, algorithm="EdDSA")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_me(raw_client, token: str):
    return raw_client.get("/api/auth/me", headers=bearer(token))


def _add_user(db, *, email: str | None, identity_user_id: str | None) -> tuple[str, str]:
    from api.db.models import Tenant, User

    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    db.add(Tenant(id=tenant_id, name=email or user_id))
    db.add(
        User(id=user_id, tenant_id=tenant_id, email=email, identity_user_id=identity_user_id)
    )
    db.commit()
    return tenant_id, user_id


def test_resolves_existing_user_by_identity_user_id(raw_client, db):
    _add_user(db, email="linked@example.com", identity_user_id="idu-linked")
    r = get_me(raw_client, make_token("idu-linked", "linked@example.com"))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "linked@example.com"


def test_links_unlinked_user_by_email_once(raw_client, db):
    from api.db.models import User

    _add_user(db, email="legacy@example.com", identity_user_id=None)
    r = get_me(raw_client, make_token("idu-new", "legacy@example.com"))
    assert r.status_code == 200, r.text
    linked = db.scalar(select(User).where(User.email == "legacy@example.com"))
    assert linked.identity_user_id == "idu-new"


def test_email_match_is_case_insensitive(raw_client, db):
    """JWT email claims arrive in whatever case the IdP stored — the local
    column is lowercased at write time, so linking must lowercase too."""
    from api.db.models import User

    _add_user(db, email="mixed@example.com", identity_user_id=None)
    r = get_me(raw_client, make_token("idu-case", "Mixed@Example.com"))
    assert r.status_code == 200, r.text
    linked = db.scalar(select(User).where(User.email == "mixed@example.com"))
    assert linked.identity_user_id == "idu-case"


def test_jit_provisions_new_tenant_and_user(raw_client, db):
    from api.db.models import Tenant, User

    r = get_me(raw_client, make_token("idu-brand-new", "new@example.com"))
    assert r.status_code == 200, r.text
    user = db.scalar(select(User).where(User.identity_user_id == "idu-brand-new"))
    assert user is not None
    assert user.email == "new@example.com"
    assert user.is_admin is False
    assert db.get(Tenant, user.tenant_id) is not None


def test_jit_provision_is_stable_across_requests(raw_client, db):
    """Second request with the same identity resolves to the SAME tenant —
    the exact anti-"always mint new" contract that fixes vires-ops#57."""
    from api.db.models import User

    tok = make_token("idu-stable", "stable@example.com")
    assert get_me(raw_client, tok).status_code == 200
    first = db.scalar(select(User).where(User.identity_user_id == "idu-stable")).tenant_id
    assert get_me(raw_client, tok).status_code == 200
    users = db.scalars(select(User).where(User.identity_user_id == "idu-stable")).all()
    assert len(users) == 1
    assert users[0].tenant_id == first


def test_email_linked_to_different_identity_conflicts(raw_client, db):
    _add_user(db, email="taken@example.com", identity_user_id="idu-original")
    r = get_me(raw_client, make_token("idu-usurper", "taken@example.com"))
    assert r.status_code == 409


def test_expired_token_rejected(raw_client, db):
    r = get_me(raw_client, make_token("idu-x", "x@example.com", expires_in=-60))
    assert r.status_code == 401


def test_wrong_issuer_rejected(raw_client, db):
    tok = make_token("idu-x", "x@example.com", issuer="https://evil.example.com")
    assert raw_client.get("/api/auth/me", headers=bearer(tok)).status_code == 401


def test_wrong_audience_rejected(raw_client, db):
    tok = make_token("idu-x", "x@example.com", audience="https://other.example.com")
    assert raw_client.get("/api/auth/me", headers=bearer(tok)).status_code == 401


def test_wrong_key_rejected(raw_client, db):
    tok = make_token("idu-x", "x@example.com", key=Ed25519PrivateKey.generate())
    assert raw_client.get("/api/auth/me", headers=bearer(tok)).status_code == 401


def test_garbage_token_rejected(raw_client, db):
    assert raw_client.get("/api/auth/me", headers=bearer("not-a-jwt")).status_code == 401


def test_missing_bearer_is_401(raw_client, db):
    """No Authorization header at all (the sole auth path since the phase-2
    cutover, vires-ops#60) is an outright 401 — there's no other path left
    to fall back to."""
    assert raw_client.get("/api/auth/me").status_code == 401


def test_non_bearer_authorization_header_is_401(raw_client, db):
    """An Authorization header present but not a Bearer scheme (e.g. Basic)
    is rejected outright, same as a missing header."""
    r = raw_client.get("/api/auth/me", headers={"Authorization": "Basic garbage"})
    assert r.status_code == 401
