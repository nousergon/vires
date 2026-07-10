"""Auth schemas — magic-link request/verify, current identity, invites."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MagicLinkRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    # Only checked for a brand-new email when require_invite_code is on
    # (returning users never need one).
    invite_code: str | None = None

    @field_validator("email")
    @classmethod
    def _lowercase_and_sanity_check(cls, v: str) -> str:
        # No `email-validator` dependency for a single field — a basic shape
        # check is enough here; Resend rejects a genuinely malformed address
        # at send time regardless.
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("not a valid email address")
        return v


class MagicLinkRequestOut(BaseModel):
    message: str


class MagicLinkVerify(BaseModel):
    token: str = Field(min_length=1)


class MeOut(BaseModel):
    email: str | None = None
    display_name: str | None = None
    is_admin: bool


class InviteCreateOut(BaseModel):
    code: str
    created_at: datetime
