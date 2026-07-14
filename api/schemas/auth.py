"""Auth schemas — current identity."""

from __future__ import annotations

from pydantic import BaseModel


class MeOut(BaseModel):
    email: str | None = None
    display_name: str | None = None
    is_admin: bool
