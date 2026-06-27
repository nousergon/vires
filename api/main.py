"""FastAPI application entrypoint.

In production the built React PWA (``web/dist``) is served as static files by
this same app, so the whole thing runs behind one uvicorn process / one nginx
upstream. During local dev the React app runs on the Vite dev server and talks
to this API over CORS.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.config import get_settings
from api.routers import exercises, health, templates, workouts

settings = get_settings()

app = FastAPI(title="Vires", version="0.1.0", description="Strength-training tracker.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health stays at root (deploy/nginx healthcheck); feature APIs live under /api
# so they never collide with the SPA's client-side routes served at root.
app.include_router(health.router)
app.include_router(exercises.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(workouts.router, prefix="/api")


def _mount_spa() -> None:
    """Serve the built PWA, with SPA fallback to index.html for client routes."""
    dist = settings.web_dist_dir
    index = os.path.join(dist, "index.html")
    if not os.path.isdir(dist) or not os.path.isfile(index):
        return  # no build present (e.g. local API-only dev) — skip silently

    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = os.path.join(dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index)


_mount_spa()
