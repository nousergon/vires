"""Web Push delivery + an in-process scheduler for locked-screen timer alerts.

When a rest/hold timer starts and the app is backgrounded (so the foreground beep
can't fire), the client asks the server to push a notification at the timer's end.
The scheduler is a simple in-process ``asyncio`` registry — fine for the single
uvicorn process; a pending alert is lost if the server restarts mid-rest (rare,
short window). Reliable-at-scale would move this to a DB-backed poller.
"""

from __future__ import annotations

import asyncio
import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import select

from api.config import get_settings
from api.db.models import PushSubscription
from api.db.session import SessionLocal

log = logging.getLogger("vires.push")

MAX_DELAY_SECONDS = 3600.0


def push_configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def _send_one(sub: PushSubscription, payload: dict) -> bool:
    """Send to one subscription. Return False if it's gone (caller deletes it)."""
    s = get_settings()
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},
            timeout=10,
        )
        return True
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):  # Gone / Not Found => dead subscription
            return False
        log.warning("push send failed (status=%s): %s", status, e)
        return True  # transient — keep the subscription


async def deliver_to_user(tenant_id: str, user_id: str, payload: dict) -> None:
    """Send `payload` to every push subscription the user has; prune dead ones."""
    with SessionLocal() as db:
        subs = db.scalars(
            select(PushSubscription).where(
                PushSubscription.tenant_id == tenant_id,
                PushSubscription.user_id == user_id,
            )
        ).all()
        for sub in subs:
            alive = await asyncio.to_thread(_send_one, sub, payload)  # webpush is blocking
            if not alive:
                db.delete(sub)
        db.commit()


# --------------------------------------------------------------------------- #
# in-process scheduler — one task per (user, timer_id), cancellable
# --------------------------------------------------------------------------- #
_tasks: dict[tuple[str, str], asyncio.Task] = {}


def cancel(user_id: str, timer_id: str) -> None:
    task = _tasks.pop((user_id, timer_id), None)
    if task and not task.done():
        task.cancel()


def schedule(
    tenant_id: str, user_id: str, timer_id: str, delay_seconds: float, payload: dict
) -> None:
    """Fire `payload` to the user after `delay_seconds`. Replaces any prior timer
    with the same id (a restarted/extended rest re-schedules cleanly)."""
    cancel(user_id, timer_id)
    delay = max(0.0, min(delay_seconds, MAX_DELAY_SECONDS))
    key = (user_id, timer_id)

    async def _run() -> None:
        try:
            await asyncio.sleep(delay)
            await deliver_to_user(tenant_id, user_id, payload)
        except asyncio.CancelledError:
            pass  # timer finished/skipped in the foreground
        except Exception:
            log.exception("scheduled push failed for user=%s timer=%s", user_id, timer_id)
        finally:
            _tasks.pop(key, None)

    _tasks[key] = asyncio.create_task(_run())
