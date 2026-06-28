"""Web Push schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeIn(BaseModel):
    endpoint: str
    keys: PushKeys


class UnsubscribeIn(BaseModel):
    endpoint: str


class ScheduleIn(BaseModel):
    timer_id: str = Field(min_length=1, max_length=128)
    delay_seconds: float = Field(ge=0, le=3600)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=300)


class CancelIn(BaseModel):
    timer_id: str = Field(min_length=1, max_length=128)


class PublicKeyOut(BaseModel):
    key: str
