"""Current-identity resolution.

Real auth (vires-ops#49): reads the ``vires_session`` cookie, hashes it, and
looks up the ``UserSession`` row — a revocable, DB-backed opaque token, not a
JWT. ``dev_auth_bypass`` (local-dev-only, see ``api.config``) skips all of
this and returns the hardcoded dev identity exactly as before auth existed;
it must never be true in a deployed ``.env``.

Every existing router keeps using ``Depends(current_identity)`` unchanged —
this is the seam the schema's ``tenant_id``/``user_id`` columns were always
built for.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Tenant, User, UserSession, UserSettings
from api.db.session import get_db

SESSION_COOKIE_NAME = "vires_session"


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    user_id: str


def hash_token(raw: str) -> str:
    """SHA-256 hex digest — used for both session tokens and magic-link
    tokens. Correct for high-entropy random values (unlike a password, there's
    no brute-force risk a slow/salted hash would need to defend against)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def current_identity(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Identity:
    settings = get_settings()
    if settings.dev_auth_bypass:
        return Identity(tenant_id=settings.dev_tenant_id, user_id=settings.dev_user_id)

    if not session_token:
        raise HTTPException(401, "Not authenticated")

    now = datetime.now(UTC)
    sess = db.get(UserSession, hash_token(session_token))
    if sess is None or sess.expires_at <= now:
        raise HTTPException(401, "Session expired or invalid")

    # Rolling refresh: a session touched within the last day gets pushed back
    # out to a full session_ttl_seconds from now (mirrors better-auth's
    # updateAge) — an abandoned session still expires on schedule.
    if (sess.expires_at - now) < timedelta(
        seconds=settings.session_ttl_seconds - settings.session_refresh_threshold_seconds
    ):
        sess.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    sess.last_seen_at = now
    db.commit()

    return Identity(tenant_id=sess.tenant_id, user_id=sess.user_id)


def ensure_dev_identity(session: Session) -> Identity:
    """Idempotently create the dev tenant + user rows. Used by seed scripts
    and the test fixture's identity override — independent of whether
    ``dev_auth_bypass`` is set."""
    s = get_settings()
    ident = Identity(tenant_id=s.dev_tenant_id, user_id=s.dev_user_id)
    if session.get(Tenant, ident.tenant_id) is None:
        session.add(Tenant(id=ident.tenant_id, name="Dev"))
    if session.get(User, ident.user_id) is None:
        session.add(
            User(id=ident.user_id, tenant_id=ident.tenant_id, display_name="Dev User")
        )
    session.commit()
    return ident


def get_or_create_settings(session: Session, ident: Identity) -> UserSettings:
    """Return the user's settings row, creating it with defaults on first access."""
    s = session.get(UserSettings, ident.user_id)
    if s is None:
        s = UserSettings(user_id=ident.user_id, tenant_id=ident.tenant_id)
        session.add(s)
        session.commit()
        session.refresh(s)
    return s
