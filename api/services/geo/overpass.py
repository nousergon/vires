"""Trail search over OpenStreetMap hiking routes via Overpass (keyless, fail-soft).

Given a name like "Mailbox Peak Trail", find matching OSM hiking/foot route
relations and return their geometry so the shared measurement engine can derive
distance + elevation. Elevation is NOT in OSM geometry — searched routes get their
elevation filled from the DEM (``elevation.fill_elevations``) downstream.

Coverage is inherently partial: OSM name search hits well-mapped named routes but
misses informal/unnamed ones — which is exactly why draw-on-map is the mandatory
fallback. Fail-soft: any Overpass error returns an empty candidate list (the UI
falls back to draw/manual), logged as WARN, never raised into the logging path.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from api.services.geo.measure import GeoPoint

log = logging.getLogger("vires.geo")

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_TIMEOUT_S = 25
_MAX_CANDIDATES = 6


@dataclass
class TrailCandidate:
    name: str
    osm_id: int
    points: list[GeoPoint]  # ordered geometry (no elevation; DEM-filled downstream)


def _build_query(name: str) -> str:
    # Case-insensitive name match on hiking/foot route relations; `out geom`
    # returns the member-way geometry so we can measure it.
    safe = name.replace("\\", "").replace('"', "")
    return (
        f"[out:json][timeout:{_TIMEOUT_S}];"
        f'rel[route~"hiking|foot"][name~"{safe}",i];'
        f"out tags geom {_MAX_CANDIDATES};"
    )


def _flatten_geometry(members: list[dict]) -> list[GeoPoint]:
    pts: list[GeoPoint] = []
    for m in members:
        for g in m.get("geometry") or []:
            lat, lon = g.get("lat"), g.get("lon")
            if lat is not None and lon is not None:
                pts.append(GeoPoint(lat=float(lat), lon=float(lon)))
    return pts


def search_trails(
    name: str, *, opener=urllib.request.urlopen
) -> list[TrailCandidate]:
    """Return up to a handful of named-trail candidates matching ``name``.

    ``opener`` is injectable for tests. Empty list on no match OR any provider
    failure (fail-soft — the caller offers draw/manual instead).
    """
    name = (name or "").strip()
    if len(name) < 3:
        return []
    body = urllib.parse.urlencode({"data": _build_query(name)}).encode("utf-8")
    req = urllib.request.Request(_OVERPASS_URL, data=body)
    try:
        with opener(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        log.warning("overpass trail search failed, offering draw/manual: %s", e)
        return []

    out: list[TrailCandidate] = []
    for el in data.get("elements", []):
        if el.get("type") != "relation":
            continue
        pts = _flatten_geometry(el.get("members") or [])
        nm = (el.get("tags") or {}).get("name")
        if nm and len(pts) >= 2:
            out.append(TrailCandidate(name=nm, osm_id=int(el["id"]), points=pts))
    return out
