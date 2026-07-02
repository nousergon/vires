"""Route geometry → distance + elevation gain.

The shared engine behind every derived activity route-input mode. Distance is the haversine
sum over the polyline. Elevation gain is the sum of positive point-to-point rises
after light smoothing (raw DEM/GPS elevation is noisy and naive summing wildly
over-counts gain). When a route's points carry no elevation (e.g. a drawn or
searched polyline), they are filled from the DEM via ``elevation.fill_elevations``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# A single route vertex. ``ele_m`` is None until filled from a DEM (or absent
# from the source, e.g. a bare drawn polyline).
@dataclass
class GeoPoint:
    lat: float
    lon: float
    ele_m: float | None = None


_EARTH_RADIUS_M = 6_371_000.0

# Ignore point-to-point rises below this (meters) as DEM/GPS noise, so cumulative
# gain isn't inflated by jitter. ~3 m is a common hiking-tracker threshold.
_ELEVATION_NOISE_FLOOR_M = 3.0


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points, meters."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = math.radians(b.lat - a.lat)
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def path_distance_m(points: list[GeoPoint]) -> float:
    """Total path length over an ordered polyline, meters."""
    return sum(haversine_m(points[i - 1], points[i]) for i in range(1, len(points)))


def elevation_gain_m(points: list[GeoPoint]) -> float | None:
    """Cumulative positive elevation gain (meters), or None if elevations are absent.

    Rises below the noise floor are dropped so DEM/GPS jitter doesn't inflate gain.
    """
    eles = [p.ele_m for p in points if p.ele_m is not None]
    if len(eles) < 2:
        return None
    gain = 0.0
    prev = eles[0]
    for e in eles[1:]:
        rise = e - prev
        if rise >= _ELEVATION_NOISE_FLOOR_M:
            gain += rise
            prev = e
        elif rise < 0:
            # Descending — advance the reference so a later climb from the low
            # point is measured from there (don't reset on tiny noise wiggles).
            prev = e
    return round(gain, 1)


@dataclass
class RouteStats:
    distance_m: float
    elevation_gain_m: float | None
    point_count: int


def measure(points: list[GeoPoint]) -> RouteStats:
    """Distance + elevation gain for a route whose points already have elevation.

    Elevation filling (for point lists without elevation) is done by the caller via
    ``elevation.fill_elevations`` before calling this — kept separate so this stays
    pure and unit-testable without any network.
    """
    if len(points) < 2:
        return RouteStats(distance_m=0.0, elevation_gain_m=None, point_count=len(points))
    return RouteStats(
        distance_m=round(path_distance_m(points), 1),
        elevation_gain_m=elevation_gain_m(points),
        point_count=len(points),
    )
