"""FastAPI application entrypoint.

In production the built React PWA (``web/dist``) is served as static files by
this same app, so the whole thing runs behind one uvicorn process / one nginx
upstream. During local dev the React app runs on the Vite dev server and talks
to this API over CORS.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.config import get_settings
from api.routers import (
    ailments,
    auth,
    coach,
    constraints,
    exercises,
    health,
    objectives,
    plan,
    push,
    records,
    routes,
    templates,
    version,
    workouts,
)
from api.routers import settings as settings_router

settings = get_settings()

app = FastAPI(title="Vires", version="0.1.0", description="Strength-training tracker.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health stays at bare root — it's hit directly against the EC2 origin by the
# deploy script / nginx healthcheck, never through the public vires.nousergon.ai
# domain (which now routes only /app* here via a Cloudflare Worker; the domain
# root belongs to the marketing/waitlist site).
app.include_router(health.router)
# Everything the browser reaches over the public domain — the SPA, its API, and
# /version (an already-open PWA's own SW-independent staleness fetch, vires-ops#59)
# — lives under /app, matching the Worker route and the app's Vite `base`.
app.include_router(version.router, prefix="/app")
app.include_router(auth.router, prefix="/app/api")
app.include_router(exercises.router, prefix="/app/api")
app.include_router(templates.router, prefix="/app/api")
app.include_router(workouts.router, prefix="/app/api")
app.include_router(settings_router.router, prefix="/app/api")
app.include_router(plan.router, prefix="/app/api")
app.include_router(coach.router, prefix="/app/api")
app.include_router(objectives.router, prefix="/app/api")
app.include_router(constraints.router, prefix="/app/api")
app.include_router(ailments.router, prefix="/app/api")
app.include_router(records.router, prefix="/app/api")
app.include_router(push.router, prefix="/app/api")
app.include_router(routes.router, prefix="/app/api")


def _safe_dist_path(dist_root: Path, full_path: str) -> Path | None:
    """Resolve ``full_path`` against ``dist_root``, or None if it would escape it.

    full_path is attacker-controlled (any %2e%2e-style segment the ASGI server
    hands the ``{path}`` converter survives — browser-level ".." collapsing
    doesn't apply to a raw HTTP client). Every file this route legitimately
    serves (manifest.json, favicon.*, the service workers — see web/public/)
    is a flat, single-segment name at dist_root's top level; nested paths
    like /app/assets/* are served by their own StaticFiles mount, never by
    this fallback. So rather than joining full_path onto dist_root and
    re-validating containment after the fact (the prior os.path.realpath +
    string-prefix approach — CodeQL's py/path-injection dataflow kept
    treating the joined result as tainted no matter how it was validated),
    take os.path.basename(full_path) up front: any ".." or "/" segment makes
    it disagree with full_path and gets rejected before dist_root is ever
    touched, which is the sanitizing pattern the query itself documents.
    """
    if not full_path:
        return None
    name = os.path.basename(full_path)
    if not name or name != full_path:
        return None
    candidate = dist_root / name
    return candidate if candidate.is_file() else None


def _mount_spa() -> None:
    """Serve the built PWA under /app, with SPA fallback for client routes."""
    dist = settings.web_dist_dir
    index = os.path.join(dist, "index.html")
    if not os.path.isdir(dist) or not os.path.isfile(index):
        return  # no build present (e.g. local API-only dev) — skip silently

    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        app.mount("/app/assets", StaticFiles(directory=assets), name="assets")

    dist_root = Path(dist).resolve()
    # Drop any spa_fallback route from a previous _mount_spa() call (tests
    # re-invoke this with a different dist_root; without this the earliest
    # registration would keep matching first forever).
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "name", None) != "spa_fallback"
    ]

    @app.get("/app/{full_path:path}", include_in_schema=False, name="spa_fallback")
    async def spa_fallback(full_path: str) -> FileResponse:
        safe = _safe_dist_path(dist_root, full_path)
        return FileResponse(safe) if safe is not None else FileResponse(index)


_mount_spa()
