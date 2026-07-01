"""Elevation + trail-search provider clients — fake opener, incl. fail-soft."""

from __future__ import annotations

import json
import urllib.error
from contextlib import contextmanager

from api.services.geo import elevation, overpass
from api.services.geo.measure import GeoPoint


def _opener_returning(payload: dict):
    @contextmanager
    def _open(_req, timeout=None):
        class _Resp:
            def read(self_inner):
                return json.dumps(payload).encode("utf-8")

        yield _Resp()

    return _open


def _opener_raising(_req, timeout=None):
    raise urllib.error.URLError("provider down")


def _opener_timeout(_req, timeout=None):
    # Read-phase timeouts surface as a BARE TimeoutError (an OSError), not wrapped
    # in URLError — the case the OSError catch must still handle fail-soft.
    raise TimeoutError("read timed out")


# --- elevation.fill_elevations -------------------------------------------- #
def test_fill_elevations_populates_missing():
    pts = [GeoPoint(47.6, -122.3), GeoPoint(47.61, -122.3)]
    opener = _opener_returning({"elevation": [50.0, 150.0]})
    filled = elevation.fill_elevations(pts, opener=opener)
    assert [p.ele_m for p in filled] == [50.0, 150.0]


def test_fill_elevations_skips_when_all_present_no_network():
    pts = [GeoPoint(47.6, -122.3, 10.0), GeoPoint(47.61, -122.3, 20.0)]
    # opener would raise if called — proves no network when nothing to fill.
    filled = elevation.fill_elevations(pts, opener=_opener_raising)
    assert [p.ele_m for p in filled] == [10.0, 20.0]


def test_fill_elevations_failsoft_returns_unchanged():
    pts = [GeoPoint(47.6, -122.3), GeoPoint(47.61, -122.3)]
    filled = elevation.fill_elevations(pts, opener=_opener_raising)
    assert all(p.ele_m is None for p in filled)  # degrades, does not raise


def test_fill_elevations_failsoft_on_readphase_timeout():
    pts = [GeoPoint(47.6, -122.3), GeoPoint(47.61, -122.3)]
    filled = elevation.fill_elevations(pts, opener=_opener_timeout)
    assert all(p.ele_m is None for p in filled)  # bare TimeoutError still caught


# --- overpass.search_trails ----------------------------------------------- #
_OVERPASS = {
    "elements": [
        {
            "type": "relation",
            "id": 42,
            "tags": {"name": "Mailbox Peak Trail", "route": "hiking"},
            "members": [
                {"geometry": [{"lat": 47.60, "lon": -121.67}, {"lat": 47.61, "lon": -121.66}]}
            ],
        }
    ]
}


def test_search_trails_returns_candidates():
    got = overpass.search_trails("Mailbox Peak", opener=_opener_returning(_OVERPASS))
    assert len(got) == 1
    assert got[0].name == "Mailbox Peak Trail"
    assert got[0].osm_id == 42
    assert len(got[0].points) == 2


def test_search_trails_short_query_skips():
    assert overpass.search_trails("ab", opener=_opener_raising) == []


def test_search_trails_failsoft_returns_empty():
    assert overpass.search_trails("Mailbox Peak", opener=_opener_raising) == []


def test_search_trails_failsoft_on_readphase_timeout():
    assert overpass.search_trails("Mailbox Peak", opener=_opener_timeout) == []
