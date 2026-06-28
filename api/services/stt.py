"""Speech-to-text via an OpenAI-compatible Whisper endpoint.

Inbound audio reaches us as a raw request body (no python-multipart dep); here we
forward it to the transcription provider as multipart over httpx. Works with
OpenAI (`whisper-1`) or Groq (set ``stt_base_url``) — both expose
``/audio/transcriptions`` with bearer auth + a ``file``/``model`` multipart form.
"""

from __future__ import annotations

import httpx

from api.config import get_settings


class STTError(RuntimeError):
    """Transcription provider returned an error (router maps to HTTP 502)."""


def _ext_for(content_type: str) -> str:
    ct = content_type.lower()
    if "mp4" in ct or "m4a" in ct or "aac" in ct:
        return "mp4"
    if "ogg" in ct or "opus" in ct:
        return "ogg"
    if "wav" in ct:
        return "wav"
    if "mpeg" in ct or "mp3" in ct:
        return "mp3"
    return "webm"


async def transcribe_audio(audio: bytes, content_type: str) -> str:
    settings = get_settings()
    filename = f"audio.{_ext_for(content_type)}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.stt_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.stt_api_key}"},
                files={"file": (filename, audio, content_type)},
                data={"model": settings.stt_model},
            )
    except httpx.HTTPError as e:
        raise STTError(f"STT request failed: {e}") from e
    if resp.status_code != 200:
        raise STTError(f"STT provider {resp.status_code}: {resp.text[:200]}")
    return (resp.json().get("text") or "").strip()
