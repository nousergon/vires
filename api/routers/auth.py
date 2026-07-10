"""Magic-link auth: request a link, verify it into a session, logout,
current identity, and admin-issued invite codes.

The emailed link points at the SPA's own `/auth/verify?token=...` page (a
plain GET pageload — harmless, doesn't consume anything), which then POSTs
the token to `verify_magic_link` below. This matters: some mail clients and
security scanners auto-fetch links via GET to scan for malware, which would
silently burn a single-use token before the real user ever opens it if the
raw email link pointed straight at a GET API endpoint.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.identity import (
    SESSION_COOKIE_NAME,
    Identity,
    current_identity,
    hash_token,
    new_opaque_token,
)
from api.db.models import InviteCode, MagicLinkToken, Tenant, User, UserSession
from api.db.session import get_db
from api.schemas.auth import (
    InviteCreateOut,
    MagicLinkRequest,
    MagicLinkRequestOut,
    MagicLinkVerify,
    MeOut,
)
from api.services.email import EmailError, send_magic_link

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=get_settings().session_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _rate_limited(db: Session, email: str) -> bool:
    settings = get_settings()
    window_start = datetime.now(UTC) - timedelta(
        seconds=settings.magic_link_rate_limit_window_seconds
    )
    count = db.scalar(
        select(func.count())
        .select_from(MagicLinkToken)
        .where(MagicLinkToken.email == email, MagicLinkToken.created_at >= window_start)
    )
    return (count or 0) >= settings.magic_link_rate_limit_per_email


def _is_bootstrap(db: Session) -> bool:
    """No REAL account has ever signed up yet. Deliberately NOT "the users
    table is empty" — the hardcoded dev user (email=None) already exists in
    every environment via `api.db.seed`'s `ensure_dev_identity` call, so an
    empty-table check would never be true and this bootstrap path would
    never fire."""
    count = db.scalar(select(func.count()).select_from(User).where(User.email.is_not(None)))
    return (count or 0) == 0


@router.post("/magic-link", response_model=MagicLinkRequestOut)
async def request_magic_link(
    body: MagicLinkRequest,
    db: Session = Depends(get_db),
) -> MagicLinkRequestOut:
    settings = get_settings()
    email = body.email

    if _rate_limited(db, email):
        raise HTTPException(429, "Too many requests — try again in a minute.")

    existing_user = db.scalar(select(User).where(User.email == email))
    recorded_invite_code: str | None = None

    if existing_user is None and settings.require_invite_code and not _is_bootstrap(db):
        if not body.invite_code:
            raise HTTPException(403, "An invite code is required to sign up.")
        invite = db.get(InviteCode, body.invite_code)
        if invite is None or invite.used_at is not None:
            raise HTTPException(403, "That invite code is invalid or already used.")
        recorded_invite_code = body.invite_code

    raw_token = new_opaque_token()
    now = datetime.now(UTC)
    db.add(
        MagicLinkToken(
            email=email,
            token_hash=hash_token(raw_token),
            invite_code=recorded_invite_code,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.magic_link_ttl_seconds),
        )
    )
    db.commit()

    link = f"{settings.frontend_url}/auth/verify?token={raw_token}"
    try:
        await send_magic_link(email, link)
    except EmailError as e:
        raise HTTPException(502, str(e)) from e

    return MagicLinkRequestOut(message="Check your email for a login link.")


@router.post("/magic-link/verify", response_model=MeOut)
def verify_magic_link(
    body: MagicLinkVerify,
    response: Response,
    db: Session = Depends(get_db),
) -> MeOut:
    now = datetime.now(UTC)
    token_hash = hash_token(body.token)

    # Atomic, race-free single-use consume — rowcount==1 iff this exact token
    # was still live; a replay or a double-click both land on rowcount==0.
    result = db.execute(
        update(MagicLinkToken)
        .where(
            MagicLinkToken.token_hash == token_hash,
            MagicLinkToken.consumed_at.is_(None),
            MagicLinkToken.expires_at > now,
        )
        .values(consumed_at=now)
    )
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(401, "This login link is invalid or has expired.")

    link_row = db.scalar(select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash))
    user = db.scalar(select(User).where(User.email == link_row.email))

    if user is None:
        is_bootstrap = _is_bootstrap(db)
        tenant_id = str(uuid.uuid4())
        db.add(Tenant(id=tenant_id, name=link_row.email))
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            email=link_row.email,
            is_admin=is_bootstrap,
        )
        db.add(user)
        db.flush()

        if not is_bootstrap and link_row.invite_code:
            consumed = db.execute(
                update(InviteCode)
                .where(InviteCode.code == link_row.invite_code, InviteCode.used_at.is_(None))
                .values(used_at=now, used_by_user_id=user.id)
            )
            if consumed.rowcount != 1:
                # Raced with another signup on the same code between request
                # and verify (already validated unused at request time, but
                # not re-checked atomically until now) — don't grant access.
                db.rollback()
                raise HTTPException(403, "That invite code was already used.")
        db.commit()

    raw_session_token = new_opaque_token()
    db.add(
        UserSession(
            id=hash_token(raw_session_token),
            user_id=user.id,
            tenant_id=user.tenant_id,
            created_at=now,
            expires_at=now + timedelta(seconds=get_settings().session_ttl_seconds),
            last_seen_at=now,
        )
    )
    db.commit()

    _set_session_cookie(response, raw_session_token)
    return MeOut(email=user.email, display_name=user.display_name, is_admin=user.is_admin)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Response:
    if session_token:
        db.execute(delete(UserSession).where(UserSession.id == hash_token(session_token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me", response_model=MeOut)
def me(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> MeOut:
    user = db.get(User, ident.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return MeOut(email=user.email, display_name=user.display_name, is_admin=user.is_admin)


@router.post("/invites", response_model=InviteCreateOut, status_code=201)
def create_invite(
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> InviteCreateOut:
    user = db.get(User, ident.user_id)
    if user is None or not user.is_admin:
        raise HTTPException(403, "Admin only")
    invite = InviteCode(code=secrets.token_hex(4), created_by_user_id=user.id)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return InviteCreateOut(code=invite.code, created_at=invite.created_at)
