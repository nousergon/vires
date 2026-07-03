"""Route-derivation endpoints backing the flexible activity route-input modes
(walk/run/hike).

- ``POST /routes/measure``   — a drawn/selected polyline → distance + elevation.
- ``GET  /routes/search``    — named-trail search over OSM (Overpass).
- ``POST /routes/import-gpx``— a GPX upload → distance + elevation + duration.

All three produce ``RouteStatsOut`` that the client drops into the (always
editable) activity distance/elevation/duration fields, then logs via
``POST /workouts/activity``. Provider calls are fail-soft (see api.services.geo).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.db.identity import Identity, current_identity
from api.schemas.routes import (
    RouteMeasureIn,
    RoutePoint,
    RouteStatsOut,
    TrailCandidate,
    TrailSearchOut,
)
from api.services.geo import elevation, overpass
from api.services.geo.gpx import GpxParseError, parse_gpx
from api.services.geo.measure import GeoPoint, measure, path_distance_m

router = APIRouter(prefix="/routes", tags=["routes"])

# 10 MB — generous for a day-hike GPX. The client POSTs the file's raw text as the
# request body (no multipart ⇒ no python-multipart dependency).
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _to_geo(points: list[RoutePoint]) -> list[GeoPoint]:
    return [GeoPoint(lat=p.lat, lon=p.lon, ele_m=p.ele_m) for p in points]


def _stats_out(pts: list[GeoPoint], *, duration_s: int | None = None) -> RouteStatsOut:
    stats = measure(pts)
    return RouteStatsOut(
        distance_m=stats.distance_m,
        elevation_gain_m=stats.elevation_gain_m,
        point_count=stats.point_count,
        duration_s=duration_s,
    )


@router.post("/measure", response_model=RouteStatsOut)
def measure_route(
    body: RouteMeasureIn,
    _ident: Identity = Depends(current_identity),
) -> RouteStatsOut:
    """Measure a drawn/selected polyline. Elevation is DEM-filled where missing;
    if the DEM is unavailable the fill is skipped (elevation_gain_m ⇒ None) and the
    user enters elevation manually — the request still succeeds."""
    pts = elevation.fill_elevations(_to_geo(body.points))
    return _stats_out(pts)


@router.get("/search", response_model=TrailSearchOut)
def search_route(
    q: str = Query(min_length=3, description="Trail/route name, e.g. 'Mailbox Peak Trail'"),
    _ident: Identity = Depends(current_identity),
) -> TrailSearchOut:
    """Search OSM hiking routes by name. Returns candidates with geometry + a rough
    distance; the client sends the chosen candidate's points to ``/routes/measure``
    for the elevation-filled stats. Empty candidates on no match; ``provider_ok``
    False on provider outage (the UI offers retry/draw/manual)."""
    result = overpass.search_trails(q)
    candidates = [
        TrailCandidate(
            osm_id=c.osm_id,
            name=c.name,
            distance_m=round(path_distance_m(c.points), 1),
            points=[RoutePoint(lat=p.lat, lon=p.lon) for p in _orient_uphill(c.points)],
        )
        for c in result.candidates
    ]
    return TrailSearchOut(candidates=candidates, provider_ok=result.provider_ok)


def _orient_uphill(pts: list[GeoPoint]) -> list[GeoPoint]:
    """Point a searched trail from its lower end to its higher end.

    OSM route relations don't encode a travel direction, and elevation gain is
    direction-dependent — a peak trail measured summit→trailhead prefills ~0
    gain. Named trails are conventionally logged uphill-first, so orient by a
    DEM lookup of just the two endpoints (one cheap batch, not the full
    geometry — that fill happens later in ``/routes/measure``). Fail-soft: if
    the DEM is down, keep the stitched order.
    """
    if len(pts) < 2:
        return pts
    ends = elevation.fill_elevations(
        [GeoPoint(lat=pts[0].lat, lon=pts[0].lon), GeoPoint(lat=pts[-1].lat, lon=pts[-1].lon)]
    )
    if ends[0].ele_m is not None and ends[-1].ele_m is not None and ends[0].ele_m > ends[-1].ele_m:
        return pts[::-1]
    return pts


@router.post("/import-gpx", response_model=RouteStatsOut)
async def import_gpx(
    request: Request,
    _ident: Identity = Depends(current_identity),
) -> RouteStatsOut:
    """Parse a GPX track (POSTed as the raw request body) → distance + elevation +
    duration. GPX usually embeds elevation; any missing points are DEM-filled."""
    raw = await request.body()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "GPX file too large (max 10 MB)")
    try:
        track = parse_gpx(raw)
    except GpxParseError as e:
        raise HTTPException(422, str(e)) from e
    pts = elevation.fill_elevations(track.points)
    return _stats_out(pts, duration_s=track.duration_s)
