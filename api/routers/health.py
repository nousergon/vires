"""Liveness endpoint — used by the deploy health check and nginx upstream."""

from __future__ import annotations

from fastapi import APIRouter

from api import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "vires", "version": __version__}
