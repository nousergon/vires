"""Schemas for the route-derivation endpoints (trail search / draw / GPX).

Every derived ruck input mode resolves to route stats (distance + elevation, plus
duration when a GPX carries timestamps) that prefill the editable ruck fields.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoutePoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    ele_m: float | None = None


class RouteMeasureIn(BaseModel):
    """A drawn/selected polyline to measure. Elevations are filled from the DEM
    server-side where absent."""

    points: list[RoutePoint] = Field(min_length=2)


class RouteStatsOut(BaseModel):
    distance_m: float
    elevation_gain_m: float | None = None
    point_count: int
    # Populated only by GPX import (from track timestamps); None otherwise.
    duration_s: int | None = None


class TrailCandidate(BaseModel):
    osm_id: int
    name: str
    distance_m: float  # from geometry (no elevation needed to rank candidates)
    points: list[RoutePoint]


class TrailSearchOut(BaseModel):
    candidates: list[TrailCandidate]
