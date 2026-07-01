"""Route-derivation endpoints (/api/routes) — providers monkeypatched off network."""

from __future__ import annotations

from api.services.geo import elevation, overpass
from api.services.geo.measure import GeoPoint

_GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="47.60" lon="-122.33"><ele>50</ele><time>2026-07-01T15:00:00Z</time></trkpt>
    <trkpt lat="47.61" lon="-122.33"><ele>250</ele><time>2026-07-01T16:00:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def test_measure_with_embedded_elevation(client):
    body = {"points": [
        {"lat": 47.60, "lon": -122.33, "ele_m": 100},
        {"lat": 47.62, "lon": -122.33, "ele_m": 300},
    ]}
    r = client.post("/api/routes/measure", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["distance_m"] > 0
    assert out["elevation_gain_m"] == 200.0
    assert out["point_count"] == 2
    assert out["duration_s"] is None  # only GPX carries duration


def test_measure_failsoft_when_dem_unavailable(client, monkeypatch):
    # No elevation on the points + DEM fill degrades → gain None, still 200.
    monkeypatch.setattr(elevation, "fill_elevations", lambda pts, **kw: pts)
    body = {"points": [{"lat": 47.60, "lon": -122.33}, {"lat": 47.62, "lon": -122.33}]}
    r = client.post("/api/routes/measure", json=body)
    assert r.status_code == 200
    assert r.json()["elevation_gain_m"] is None


def test_measure_rejects_single_point(client):
    r = client.post("/api/routes/measure", json={"points": [{"lat": 1, "lon": 1}]})
    assert r.status_code == 422  # min_length=2


def test_search_returns_candidates(client, monkeypatch):
    monkeypatch.setattr(
        overpass,
        "search_trails",
        lambda q, **kw: [
            overpass.TrailCandidate(
                name="Mailbox Peak Trail",
                osm_id=42,
                points=[GeoPoint(47.60, -121.67), GeoPoint(47.62, -121.66)],
            )
        ],
    )
    r = client.get("/api/routes/search", params={"q": "Mailbox Peak"})
    assert r.status_code == 200
    cands = r.json()["candidates"]
    assert len(cands) == 1
    assert cands[0]["name"] == "Mailbox Peak Trail"
    assert cands[0]["distance_m"] > 0
    assert len(cands[0]["points"]) == 2


def test_search_short_query_rejected(client):
    assert client.get("/api/routes/search", params={"q": "ab"}).status_code == 422


def test_import_gpx_derives_distance_elevation_duration(client):
    r = client.post("/api/routes/import-gpx", content=_GPX)
    assert r.status_code == 200
    out = r.json()
    assert out["distance_m"] > 0
    assert out["elevation_gain_m"] == 200.0
    assert out["duration_s"] == 3600


def test_import_gpx_rejects_malformed(client):
    r = client.post("/api/routes/import-gpx", content="not gpx <<<")
    assert r.status_code == 422
