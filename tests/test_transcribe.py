"""Coach speech-to-text endpoint (provider call is mocked — no network)."""

from __future__ import annotations

import pytest

from api.services import stt


def _set_key(monkeypatch, key="test-stt-key"):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "stt_api_key", key)


def test_transcribe_returns_text(client, monkeypatch):
    async def fake(audio: bytes, content_type: str) -> str:
        assert audio == b"fake-audio-bytes"
        return "bench press three sets of eight"

    _set_key(monkeypatch)
    monkeypatch.setattr("api.routers.coach.transcribe_audio", fake)
    resp = client.post(
        "/app/api/coach/transcribe",
        content=b"fake-audio-bytes",
        headers={"content-type": "audio/webm"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "bench press three sets of eight"


def test_transcribe_503_without_key(client, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "stt_api_key", None)
    resp = client.post(
        "/app/api/coach/transcribe", content=b"x", headers={"content-type": "audio/webm"}
    )
    assert resp.status_code == 503


def test_transcribe_400_on_empty_body(client, monkeypatch):
    _set_key(monkeypatch)
    resp = client.post(
        "/app/api/coach/transcribe", content=b"", headers={"content-type": "audio/webm"}
    )
    assert resp.status_code == 400


def test_transcribe_502_on_provider_error(client, monkeypatch):
    async def boom(audio: bytes, content_type: str) -> str:
        raise stt.STTError("provider 500: upstream down")

    _set_key(monkeypatch)
    monkeypatch.setattr("api.routers.coach.transcribe_audio", boom)
    resp = client.post(
        "/app/api/coach/transcribe", content=b"abc", headers={"content-type": "audio/webm"}
    )
    assert resp.status_code == 502


@pytest.mark.parametrize(
    "content_type,expected_ext",
    [
        ("audio/webm", "webm"),
        ("audio/mp4", "mp4"),
        ("audio/ogg;codecs=opus", "ogg"),
        ("audio/wav", "wav"),
        ("audio/mpeg", "mp3"),
        ("application/octet-stream", "webm"),
    ],
)
def test_ext_for_content_type(content_type, expected_ext):
    assert stt._ext_for(content_type) == expected_ext
