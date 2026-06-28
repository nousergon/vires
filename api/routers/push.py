"""Web Push: subscribe a device + schedule/cancel a timer-end notification.

The client schedules a push when a running timer is backgrounded and cancels it on
return to the foreground, so the locked-screen case gets a notification without
double-alerting when the app is visible (the in-app beep handles that).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.identity import Identity, current_identity
from api.db.models import PushSubscription
from api.db.session import get_db
from api.schemas.push import (
    CancelIn,
    PublicKeyOut,
    ScheduleIn,
    SubscribeIn,
    UnsubscribeIn,
)
from api.services import push as push_service

router = APIRouter(prefix="/push", tags=["push"])


def _require_configured() -> None:
    if not push_service.push_configured():
        raise HTTPException(503, "Push notifications are not configured.")


@router.get("/public-key", response_model=PublicKeyOut)
def public_key() -> PublicKeyOut:
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(503, "Push notifications are not configured.")
    return PublicKeyOut(key=key)


@router.post("/subscribe", status_code=204)
def subscribe(
    body: SubscribeIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    _require_configured()
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    sub.tenant_id = ident.tenant_id
    sub.user_id = ident.user_id
    sub.p256dh = body.keys.p256dh
    sub.auth = body.keys.auth
    db.commit()
    return Response(status_code=204)


@router.post("/unsubscribe", status_code=204)
def unsubscribe(
    body: UnsubscribeIn,
    db: Session = Depends(get_db),
    ident: Identity = Depends(current_identity),
) -> Response:
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == ident.user_id,
        )
    )
    if sub is not None:
        db.delete(sub)
        db.commit()
    return Response(status_code=204)


@router.post("/schedule", status_code=202)
async def schedule_push(
    body: ScheduleIn,
    ident: Identity = Depends(current_identity),
) -> Response:
    _require_configured()
    push_service.schedule(
        ident.tenant_id,
        ident.user_id,
        body.timer_id,
        body.delay_seconds,
        {"title": body.title, "body": body.body},
    )
    return Response(status_code=202)


@router.post("/cancel", status_code=202)
async def cancel_push(
    body: CancelIn,
    ident: Identity = Depends(current_identity),
) -> Response:
    push_service.cancel(ident.user_id, body.timer_id)
    return Response(status_code=202)
