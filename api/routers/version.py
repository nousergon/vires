"""Deployed build-id endpoint (vires-ops#59).

Reports the build-id (git SHA in CI, else the local short SHA) of the frontend
bundle currently on disk — ``web/dist/version.json``, written by the Vite build.

This is served here by FastAPI, deliberately NOT as a precached static asset, so
an already-open PWA can detect staleness with a plain ``fetch('/version')`` even
when the service worker's own ``autoUpdate`` path is wedged (the failure that
left an installed app silently running 5-day-old JS on 2026-07-10). Because the
response carries ``Cache-Control: no-store`` and the route is not a navigation
request, neither the HTTP cache nor the Workbox SW ever hands back a stale copy
of it — so the staleness signal keeps working even if the SW update path breaks
again.

Kept at root (like ``/health``), registered before the SPA catch-all in
``api.main`` so it resolves ahead of the ``/{full_path:path}`` fallback.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.config import get_settings

router = APIRouter(tags=["version"])

# Sentinel returned when no build is on disk (local API-only dev) or the file is
# unreadable. The frontend treats it as "can't tell" and never shows the banner,
# so a missing/garbled file degrades to silence rather than a false alarm.
UNKNOWN = "unknown"


def read_build_id() -> str:
    """Build-id of the bundle on disk, or ``"unknown"`` when absent/unreadable.

    Read per request (the file is a few bytes and the process is restarted on
    every deploy) so a hot-swapped bundle is reflected without a stale cache.
    """
    settings = get_settings()
    path = os.path.join(settings.web_dist_dir, "version.json")
    try:
        with open(path, encoding="utf-8") as f:
            build_id = json.load(f).get("buildId")
    except (OSError, ValueError):
        return UNKNOWN
    return build_id if isinstance(build_id, str) and build_id else UNKNOWN


@router.get("/version")
async def version() -> JSONResponse:
    return JSONResponse(
        {"buildId": read_build_id()},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
