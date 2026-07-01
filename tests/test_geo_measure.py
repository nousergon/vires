"""Shared route measurement engine — pure unit tests (no network)."""

from __future__ import annotations

from api.services.geo.measure import (
    GeoPoint,
    elevation_gain_m,
    haversine_m,
    measure,
    path_distance_m,
)


def test_haversine_known_distance():
    # ~1 degree of latitude ≈ 111 km.
    d = haversine_m(GeoPoint(0, 0), GeoPoint(1, 0))
    assert 110_000 < d < 112_000


def test_path_distance_sums_segments():
    pts = [GeoPoint(0, 0), GeoPoint(0, 1), GeoPoint(0, 2)]
    total = path_distance_m(pts)
    seg = haversine_m(GeoPoint(0, 0), GeoPoint(0, 1))
    assert abs(total - 2 * seg) < 1e-6


def test_elevation_gain_counts_only_rises_above_noise_floor():
    # Net climb 100→130 with a small dip; sub-3m wiggles ignored.
    pts = [
        GeoPoint(0, 0, 100),
        GeoPoint(0, 1, 101),  # +1 (noise, dropped)
        GeoPoint(0, 2, 130),  # +30 from 100 baseline once it clears the floor
        GeoPoint(0, 3, 120),  # descent
        GeoPoint(0, 4, 150),  # +30 from the low point
    ]
    gain = elevation_gain_m(pts)
    assert gain is not None and 55 <= gain <= 65  # ~30 + ~30


def test_elevation_gain_none_without_elevations():
    assert elevation_gain_m([GeoPoint(0, 0), GeoPoint(0, 1)]) is None


def test_measure_short_route_is_zero():
    stats = measure([GeoPoint(0, 0)])
    assert stats.distance_m == 0.0 and stats.elevation_gain_m is None


def test_measure_full_route():
    pts = [GeoPoint(0, 0, 100), GeoPoint(0, 1, 200)]
    stats = measure(pts)
    assert stats.point_count == 2
    assert stats.distance_m > 0
    assert stats.elevation_gain_m == 100.0
