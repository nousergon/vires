"""Trail search over OpenStreetMap hiking routes via Overpass (keyless, fail-soft).

Given a name like "Mailbox Peak Trail", find matching OSM hiking/foot route
relations and return their geometry so the shared measurement engine can derive
distance + elevation. Elevation is NOT in OSM geometry — searched routes get their
elevation filled from the DEM (``elevation.fill_elevations``) downstream.

Coverage is inherently partial: OSM name search hits well-mapped named routes but
misses informal/unnamed ones — which is exactly why draw-on-map is the mandatory
fallback. Fail-soft: any Overpass error returns an empty candidate list (the UI
falls back to draw/manual), logged as WARN, never raised into the logging path —
but the failure is still distinguished from a genuine no-match (``provider_ok``)
so the UI never tells the user "no matching trails" during a provider outage.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass

from api.services.geo.measure import GeoPoint, path_distance_m

log = logging.getLogger("vires.geo")

# Primary + mirror, tried in order. The main overpass-api.de instance is a
# shared public server that regularly answers "server too busy" / rate-limits;
# kumi.systems runs a high-capacity public mirror of the same API.
_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_TIMEOUT_S = 25
_MAX_CANDIDATES = 6
# OSM operational policy requires an identifying User-Agent; the main
# overpass-api.de instance answers HTTP 406 to Python's default
# "Python-urllib/3.x" UA, so without this header every search fails even
# with a correct query (verified live 2026-07-03).
_USER_AGENT = "vires/0.1 (+https://github.com/nousergon/vires)"


@dataclass
class TrailCandidate:
    name: str
    osm_id: int
    points: list[GeoPoint]  # ordered geometry (no elevation; DEM-filled downstream)


@dataclass
class TrailSearchResult:
    """Candidates + whether the provider actually answered. ``provider_ok`` is
    False only when every Overpass endpoint failed — an empty candidate list
    with ``provider_ok=True`` is a real "OSM has no such named route"."""

    candidates: list[TrailCandidate]
    provider_ok: bool


def _build_query(name: str) -> str:
    # Case-insensitive name match on hiking/foot route relations; `out geom`
    # returns the member-way geometry so we can measure it. The verbosity must
    # stay body-level (`out geom`, never `out tags geom`): `tags` verbosity
    # suppresses relation members entirely, so the `geom` modifier has nothing
    # to attach geometry to, every candidate fails the >=2-points filter, and
    # search returns empty even for trails OSM has (e.g. Mailbox Peak Trail,
    # relation 5426108).
    safe = name.replace("\\", "").replace('"', "")
    return (
        f"[out:json][timeout:{_TIMEOUT_S}];"
        f'rel[route~"hiking|foot"][name~"{safe}",i];'
        f"out geom {_MAX_CANDIDATES};"
    )


def _member_ways(members: list[dict]) -> list[list[GeoPoint]]:
    ways: list[list[GeoPoint]] = []
    for m in members:
        pts = [
            GeoPoint(lat=float(g["lat"]), lon=float(g["lon"]))
            for g in m.get("geometry") or []
            if g.get("lat") is not None and g.get("lon") is not None
        ]
        if len(pts) >= 2:
            ways.append(pts)
    return ways


def _close(a: GeoPoint, b: GeoPoint) -> bool:
    # Member ways of a relation share exact endpoint nodes; a hair of slack
    # covers float round-tripping. ~1e-5 deg ≈ 1 m.
    return abs(a.lat - b.lat) < 1e-5 and abs(a.lon - b.lon) < 1e-5


def _stitch_route(members: list[dict]) -> list[GeoPoint]:
    """Order a relation's member ways into the longest continuous chain.

    Relation members arrive in arbitrary order and orientation, and one
    relation often bundles several physical trails (Mailbox Peak's relation
    carries both the old and new trails). Naively concatenating every member
    zigzags between them, inflating distance and (via phantom climbs)
    elevation gain ~2-3x. So: greedily chain ways whose endpoints touch
    (reversing as needed), then keep the longest chain — the main route.
    The prefilled fields stay user-editable, so a variant mismatch is a
    one-tap correction rather than a silently wrong number.
    """
    remaining = _member_ways(members)
    chains: list[list[GeoPoint]] = []
    while remaining:
        chain = remaining.pop(0)
        grew = True
        while grew:
            grew = False
            for i, way in enumerate(remaining):
                if _close(chain[-1], way[0]):
                    chain = chain + way[1:]
                elif _close(chain[-1], way[-1]):
                    chain = chain + way[-2::-1]
                elif _close(chain[0], way[-1]):
                    chain = way + chain[1:]
                elif _close(chain[0], way[0]):
                    chain = way[::-1] + chain[1:]
                else:
                    continue
                remaining.pop(i)
                grew = True
                break
        chains.append(chain)
    if not chains:
        return []
    return max(chains, key=path_distance_m)


def search_trails(
    name: str, *, opener=urllib.request.urlopen
) -> TrailSearchResult:
    """Return up to a handful of named-trail candidates matching ``name``.

    ``opener`` is injectable for tests. Tries the primary Overpass instance,
    then the mirror; fail-soft on total failure (empty candidates +
    ``provider_ok=False`` — the caller offers retry/draw/manual instead).
    """
    name = (name or "").strip()
    if len(name) < 3:
        return TrailSearchResult(candidates=[], provider_ok=True)
    body = urllib.parse.urlencode({"data": _build_query(name)}).encode("utf-8")

    data: dict | None = None
    for url in _OVERPASS_URLS:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": _USER_AGENT})
        try:
            with opener(req, timeout=_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except (OSError, ValueError) as e:
            # OSError subsumes URLError + read-phase TimeoutError + socket
            # errors — a URLError-only catch misses bare TimeoutError from
            # getresponse(). ValueError covers non-JSON bodies (the "server
            # too busy" HTML error page comes back as HTTP 200).
            log.warning("overpass trail search failed on %s: %s", url, e)
    if data is None:
        log.warning("overpass trail search failed on all endpoints, offering draw/manual")
        return TrailSearchResult(candidates=[], provider_ok=False)

    out: list[TrailCandidate] = []
    for el in data.get("elements", []):
        if el.get("type") != "relation":
            continue
        pts = _stitch_route(el.get("members") or [])
        nm = (el.get("tags") or {}).get("name")
        if nm and len(pts) >= 2:
            out.append(TrailCandidate(name=nm, osm_id=int(el["id"]), points=pts))
    return TrailSearchResult(candidates=out, provider_ok=True)
