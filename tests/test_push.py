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
    assert client.get("/app/api/push/public-key").status_code == 503


def test_public_key_with_config(client, monkeypatch):
    _configure(monkeypatch)
    r = client.get("/app/api/push/public-key")
    assert r.status_code == 200 and r.json()["key"] == "BTestPublicKey"


def test_subscribe_503_without_config(client):
    assert client.post("/app/api/push/subscribe", json=_SUB).status_code == 503


def test_schedule_503_without_config(client):
    body = {"timer_id": "t1", "delay_seconds": 5, "title": "Rest over"}
    assert client.post("/app/api/push/schedule", json=body).status_code == 503


# --------------------------------------------------------------------------- #
# subscription CRUD
# --------------------------------------------------------------------------- #
def test_subscribe_is_idempotent_upsert(client, db, monkeypatch):
    _configure(monkeypatch)
    assert client.post("/app/api/push/subscribe", json=_SUB).status_code == 204
    # same endpoint again — updates, doesn't duplicate
    assert client.post("/app/api/push/subscribe", json=_SUB).status_code == 204
    rows = db.query(PushSubscription).filter_by(endpoint=_SUB["endpoint"]).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "p256" and rows[0].auth == "auth"


def test_unsubscribe_removes_row(client, db, monkeypatch):
    _configure(monkeypatch)
    client.post("/app/api/push/subscribe", json=_SUB)
    r = client.post("/app/api/push/unsubscribe", json={"endpoint": _SUB["endpoint"]})
    assert r.status_code == 204
    assert db.query(PushSubscription).filter_by(endpoint=_SUB["endpoint"]).count() == 0


def test_schedule_and_cancel_return_202(client, monkeypatch):
    _configure(monkeypatch)
    calls = {}
    monkeypatch.setattr(push, "schedule", lambda *a, **k: calls.setdefault("schedule", a))
    monkeypatch.setattr(push, "cancel", lambda *a, **k: calls.setdefault("cancel", a))
    r1 = client.post(
        "/app/api/push/schedule",
        json={"timer_id": "t1", "delay_seconds": 5, "title": "Rest over", "body": "x"},
    )
    r2 = client.post("/app/api/push/cancel", json={"timer_id": "t1"})
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


# --------------------------------------------------------------------------- #
# log sanitization  (CodeQL py/log-injection guard)
# --------------------------------------------------------------------------- #
def test_sanitize_passes_clean_string_through():
    """Normal values are not altered."""
    assert push._sanitize("hello-world") == "hello-world"
    assert push._sanitize("timer_42") == "timer_42"
    assert push._sanitize("user_uuid_abc") == "user_uuid_abc"


def test_sanitize_strips_control_chars():
    """CR (\r), null (\x00), and other control chars (except tab, newline) are stripped."""
    assert push._sanitize("foo\rbar") == "foobar"
    assert push._sanitize("foo\x00bar") == "foobar"
    assert push._sanitize("foo\x01bar") == "foobar"
    assert push._sanitize("foo\x1fbar") == "foobar"


def test_sanitize_keeps_tab():
    """Tab (0x09) — legitimate whitespace — survives."""
    assert push._sanitize("foo\tbar") == "foo\tbar"


def test_sanitize_strips_newlines():
    """Newline (0x0a) — the primary log-forging vector — is stripped."""
    assert push._sanitize("foo\nbar") == "foobar"


def test_sanitize_empty():
    """Empty string stays empty."""
    assert push._sanitize("") == ""
    assert push._sanitize("a\r\nb") == "ab"
    assert push._sanitize("\r\n") == ""


def test_sanitize_none_and_c1_controls():
    """Regression for alpha-engine-config-I8019: no input bypasses the replace
    calls (the old early ``return s`` handed back the raw value), and DEL/C1
    controls are stripped too."""
    assert push._sanitize(None) == ""
    assert push._sanitize("a\x7fb\x85c\x9fd") == "abcd"


def test_scheduled_push_failure_log_is_single_line(monkeypatch, caplog):
    """A CR/LF-bearing user_id/timer_id cannot forge a second log line."""
    import logging

    async def boom(tenant, user, payload):
        raise RuntimeError("delivery failed")

    monkeypatch.setattr(push, "deliver_to_user", boom)

    async def run():
        push.schedule("tn", "u9\r\nFORGED", "t9\nFORGED", 0.0, {"title": "x", "body": ""})
        await asyncio.sleep(0.05)

    with caplog.at_level(logging.ERROR, logger="vires.push"):
        asyncio.run(run())
    msgs = [r.getMessage() for r in caplog.records if r.name == "vires.push"]
    assert msgs == ["scheduled push failed for user=u9FORGED timer=t9FORGED"]


def test_send_failure_log_is_single_line(monkeypatch, caplog):
    """The push service's error text is externally sourced: it is sanitised too."""
    import logging

    from pywebpush import WebPushException

    def raise_wpe(**kwargs):
        raise WebPushException("upstream said\r\nCRITICAL forged")

    monkeypatch.setattr(push, "webpush", raise_wpe)
    sub = PushSubscription(endpoint="https://push.example.invalid/x", p256dh="k", auth="a")
    with caplog.at_level(logging.WARNING, logger="vires.push"):
        assert push._send_one(sub, {"title": "x"}) is True
    msgs = [r.getMessage() for r in caplog.records if r.name == "vires.push"]
    assert len(msgs) == 1
    assert "\n" not in msgs[0] and "\r" not in msgs[0]
    assert "CRITICAL forged" in msgs[0]
