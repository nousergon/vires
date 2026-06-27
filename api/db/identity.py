"""Current-identity resolution.

MVP: a single hardcoded dev tenant + user (from settings). This is the seam
where real auth lands later — swap ``current_identity`` for a session/JWT
resolver and every query that already filters by ``tenant_id``/``user_id``
becomes multi-tenant with no schema change.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Tenant, User, UserSettings


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    user_id: str


def current_identity() -> Identity:
    s = get_settings()
    return Identity(tenant_id=s.dev_tenant_id, user_id=s.dev_user_id)


def ensure_dev_identity(session: Session) -> Identity:
    """Idempotently create the dev tenant + user rows."""
    ident = current_identity()
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
