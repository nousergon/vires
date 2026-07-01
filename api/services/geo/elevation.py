"""Fill route points with elevation from the Open-Meteo DEM (keyless, fail-soft).

Open-Meteo's elevation endpoint serves Copernicus/SRTM DEM data with no API key
and permissive CORS. Used when a route's geometry carries no elevation of its own
(a drawn polyline, or some searched trails). GPX tracks usually embed elevation
and skip this.

Fail-soft contract: any provider/parse/network error leaves points UNCHANGED
(elevations stay None ⇒ the caller reports elevation gain as None and the user
enters it manually). We never raise into the ruck-logging path over a DEM outage —
but we DO log a WARN so the degradation is visible, not silently swallowed.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from api.services.geo.measure import GeoPoint

log = logging.getLogger("vires.geo")

_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
_BATCH = 100  # Open-Meteo accepts up to 100 coordinates per request
_TIMEOUT_S = 8


def _fetch_batch(batch: list[GeoPoint], *, opener=urllib.request.urlopen) -> list[float] | None:
    lats = ",".join(f"{p.lat:.6f}" for p in batch)
    lons = ",".join(f"{p.lon:.6f}" for p in batch)
    url = f"{_ELEVATION_URL}?latitude={lats}&longitude={lons}"
    try:
        with opener(url, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elevations = data.get("elevation")
        if not isinstance(elevations, list) or len(elevations) != len(batch):
            log.warning("open-meteo elevation: unexpected shape (%s pts)", len(batch))
            return None
        return [float(e) for e in elevations]
    except (OSError, ValueError, KeyError) as e:
        # OSError subsumes URLError + read-phase TimeoutError + socket errors —
        # a URLError-only catch misses bare TimeoutError from getresponse().
        log.warning("open-meteo elevation fetch failed, degrading to manual: %s", e)
        return None


def fill_elevations(
    points: list[GeoPoint], *, opener=urllib.request.urlopen
) -> list[GeoPoint]:
    """Return points with ``ele_m`` filled from the DEM where missing.

    Points that already have elevation are left as-is. On any provider failure the
    input is returned unchanged (fail-soft). ``opener`` is injectable for tests.
    """
    need_idx = [i for i, p in enumerate(points) if p.ele_m is None]
    if not need_idx:
        return points

    filled = list(points)
    for start in range(0, len(need_idx), _BATCH):
        idx_batch = need_idx[start : start + _BATCH]
        got = _fetch_batch([points[i] for i in idx_batch], opener=opener)
        if got is None:
            return points  # fail-soft: abandon filling, keep originals
        for i, ele in zip(idx_batch, got, strict=True):
            filled[i] = GeoPoint(lat=points[i].lat, lon=points[i].lon, ele_m=ele)
    return filled
