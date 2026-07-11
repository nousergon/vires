"""Current-identity resolution.

Two authentication paths coexist during the shared-identity cutover
(vires-ops#60, phase 1 — non-destructive):

- **Bearer JWT (new, preferred):** an ``Authorization: Bearer <jwt>`` header
  carrying a short-lived token minted by the shared nousergon-auth service,
  verified locally against its JWKS (see ``api.services.auth_jwt``). The
  verified ``sub`` claim resolves to a local ``User`` via the
  ``identity_user_id`` column — matched by id first, then linked once by
  email, else JIT-provisioned (the deliberate, planned version of the
  backfill vires-ops#57 needed reactively).

- **Legacy session cookie (vires-ops#49):** the ``vires_session`` cookie,
  hashed and looked up in ``UserSession``. Retired — endpoints and tables
  dropped — only in a later migration AFTER the JWT path is verified live.

``dev_auth_bypass`` (local-dev-only, see ``api.config``) skips all of this
and returns the hardcoded dev identity; it must never be true in a deployed
``.env``. Every existing router keeps using ``Depends(current_identity)``
unchanged — this is the seam the schema's ``tenant_id``/``user_id`` columns
were always built for.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Tenant, User, UserSession, UserSettings
from api.db.session import get_db
from api.services.auth_jwt import IdentityTokenError, verify_identity_token

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


def _resolve_identity_user(db: Session, sub: str, email: str | None) -> User:
    """Map a verified nousergon-auth identity to a local ``User`` row.

    Resolution ladder (vires-ops#60): match by ``identity_user_id``; else
    link once by email (only onto a row not yet linked to a DIFFERENT
    identity); else JIT-provision a fresh ``Tenant`` + ``User``. This is the
    contract that replaces verify-time "always mint new" — the root cause of
    the vires-ops#57 data-orphaning incident.
    """
    user = db.scalar(select(User).where(User.identity_user_id == sub))
    if user is not None:
        return user

    if email:
        by_email = db.scalar(select(User).where(User.email == email))
        if by_email is not None:
            if by_email.identity_user_id is not None:
                # Same email, different identity id: the shared service's
                # account for this address was recreated out from under the
                # link. Silently re-linking would hand the new identity the
                # old identity's data — refuse loudly instead; resolving this
                # is an explicit operator action.
                raise HTTPException(
                    409,
                    "This email is already linked to a different identity — "
                    "contact the administrator.",
                )
            by_email.identity_user_id = sub
            db.commit()
            return by_email

    tenant_id = str(uuid.uuid4())
    db.add(Tenant(id=tenant_id, name=email or sub))
    user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        email=email,
        identity_user_id=sub,
        is_admin=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent first requests for the same brand-new identity both
        # reached the JIT-provision branch; the unique index on
        # identity_user_id (or email) let exactly one win. Recover by
        # re-reading the winner — anything still missing after that is a real
        # invariant violation and re-raises.
        db.rollback()
        user = db.scalar(select(User).where(User.identity_user_id == sub))
        if user is None:
            raise
    return user


def _identity_from_bearer(db: Session, token: str) -> Identity:
    try:
        claims = verify_identity_token(token)
    except IdentityTokenError as e:
        raise HTTPException(401, "Invalid or expired token") from e
    user = _resolve_identity_user(db, claims.sub, claims.email)
    return Identity(tenant_id=user.tenant_id, user_id=user.id)


def current_identity(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> Identity:
    settings = get_settings()
    if settings.dev_auth_bypass:
        return Identity(tenant_id=settings.dev_tenant_id, user_id=settings.dev_user_id)

    # A presented bearer token is authoritative: it either verifies or the
    # request is 401 — no silent fallback to the cookie path, which would let
    # a broken/expired token mask itself behind a stale session.
    if authorization is not None and authorization.lower().startswith("bearer "):
        return _identity_from_bearer(db, authorization[7:].strip())

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
