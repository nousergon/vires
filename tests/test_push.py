"""Web Push: subscribe/unsubscribe + config gating + the async scheduler."""

from __future__ import annotations

import asyncio

from api.db.models import PushSubscription
from api.services import push


def _configure(monkeypatch):
    from api.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", "BTestPublicKey")
    monkeypatch.setattr(s, "vapid_private_key", "test-private-key")


_SUB = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "p256", "auth": "auth"}}


# --------------------------------------------------------------------------- #
# config gating
# --------------------------------------------------------------------------- #
def test_public_key_503_without_config(client):
    assert client.get("/api/push/public-key").status_code == 503


def test_public_key_with_config(client, monkeypatch):
    _configure(monkeypatch)
    r = client.get("/api/push/public-key")
    assert r.status_code == 200 and r.json()["key"] == "BTestPublicKey"


def test_subscribe_503_without_config(client):
    assert client.post("/api/push/subscribe", json=_SUB).status_code == 503


def test_schedule_503_without_config(client):
    body = {"timer_id": "t1", "delay_seconds": 5, "title": "Rest over"}
    assert client.post("/api/push/schedule", json=body).status_code == 503


# --------------------------------------------------------------------------- #
# subscription CRUD
# --------------------------------------------------------------------------- #
def test_subscribe_is_idempotent_upsert(client, db, monkeypatch):
    _configure(monkeypatch)
    assert client.post("/api/push/subscribe", json=_SUB).status_code == 204
    # same endpoint again — updates, doesn't duplicate
    assert client.post("/api/push/subscribe", json=_SUB).status_code == 204
    rows = db.query(PushSubscription).filter_by(endpoint=_SUB["endpoint"]).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "p256" and rows[0].auth == "auth"


def test_unsubscribe_removes_row(client, db, monkeypatch):
    _configure(monkeypatch)
    client.post("/api/push/subscribe", json=_SUB)
    r = client.post("/api/push/unsubscribe", json={"endpoint": _SUB["endpoint"]})
    assert r.status_code == 204
    assert db.query(PushSubscription).filter_by(endpoint=_SUB["endpoint"]).count() == 0


def test_schedule_and_cancel_return_202(client, monkeypatch):
    _configure(monkeypatch)
    calls = {}
    monkeypatch.setattr(push, "schedule", lambda *a, **k: calls.setdefault("schedule", a))
    monkeypatch.setattr(push, "cancel", lambda *a, **k: calls.setdefault("cancel", a))
    r1 = client.post(
        "/api/push/schedule",
        json={"timer_id": "t1", "delay_seconds": 5, "title": "Rest over", "body": "x"},
    )
    r2 = client.post("/api/push/cancel", json={"timer_id": "t1"})
    assert r1.status_code == 202 and r2.status_code == 202
    assert "schedule" in calls and "cancel" in calls


# --------------------------------------------------------------------------- #
# the in-process scheduler (real, with deliver mocked)
# --------------------------------------------------------------------------- #
def test_scheduler_fires_after_delay(monkeypatch):
    delivered: list = []

    async def fake_deliver(tenant, user, payload):
        delivered.append((user, payload))

    monkeypatch.setattr(push, "deliver_to_user", fake_deliver)

    async def run():
        push.schedule("tn", "u1", "timer1", 0.05, {"title": "Rest over", "body": ""})
        await asyncio.sleep(0.15)

    asyncio.run(run())
    assert delivered == [("u1", {"title": "Rest over", "body": ""})]


def test_scheduler_cancel_prevents_fire(monkeypatch):
    delivered: list = []

    async def fake_deliver(tenant, user, payload):
        delivered.append(user)

    monkeypatch.setattr(push, "deliver_to_user", fake_deliver)

    async def run():
        push.schedule("tn", "u2", "timer2", 0.2, {"title": "Rest over", "body": ""})
        await asyncio.sleep(0.02)
        push.cancel("u2", "timer2")
        await asyncio.sleep(0.25)

    asyncio.run(run())
    assert delivered == []


def test_schedule_replaces_same_timer_id(monkeypatch):
    delivered: list = []

    async def fake_deliver(tenant, user, payload):
        delivered.append(payload["title"])

    monkeypatch.setattr(push, "deliver_to_user", fake_deliver)

    async def run():
        push.schedule("tn", "u3", "timer3", 0.3, {"title": "OLD", "body": ""})
        await asyncio.sleep(0.02)
        push.schedule("tn", "u3", "timer3", 0.05, {"title": "NEW", "body": ""})  # replaces
        await asyncio.sleep(0.2)

    asyncio.run(run())
    assert delivered == ["NEW"]  # the old one was cancelled
