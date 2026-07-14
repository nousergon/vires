"""Current-identity probe.

Sign-in itself lives entirely on the shared nousergon-auth service (the SPA
talks to it directly via the better-auth client — see `web/src/lib/authClient.ts`).
The only thing Vires's own API still needs to expose is `/auth/me`, which
resolves whatever identity `current_identity` (see `api.db.identity`)
produced — bearer-JWT verified against the shared service, the sole
authentication path since the phase-2 shared-identity migration
(vires-ops#60) retired the legacy magic-link/session/allowlist endpoints and
their backing tables.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db.identity import Identity, current_identity
from api.db.models import User
from api.db.session import get_db
from api.schemas.auth import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
def me(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> MeOut:
    user = db.get(User, ident.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return MeOut(email=user.email, display_name=user.display_name, is_admin=user.is_admin)
