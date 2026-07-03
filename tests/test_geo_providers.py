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
    assert got.provider_ok is True
    assert len(got.candidates) == 1
    assert got.candidates[0].name == "Mailbox Peak Trail"
    assert got.candidates[0].osm_id == 42
    assert len(got.candidates[0].points) == 2


def _g(lat, lon):
    return {"lat": lat, "lon": lon}


def test_stitch_orders_and_reverses_member_ways():
    # Members arrive out of order and orientation; stitching must produce one
    # continuous chain a→b→c→d (either travel direction — OSM relations don't
    # encode one; the search endpoint orients uphill afterwards).
    members = [
        {"geometry": [_g(2.0, 0.0), _g(1.0, 0.0)]},  # reversed middle leg
        {"geometry": [_g(0.0, 0.0), _g(1.0, 0.0)]},  # first leg
        {"geometry": [_g(2.0, 0.0), _g(3.0, 0.0)]},  # last leg
    ]
    chain = overpass._stitch_route(members)
    lats = [p.lat for p in chain]
    assert lats in ([0.0, 1.0, 2.0, 3.0], [3.0, 2.0, 1.0, 0.0])


def test_stitch_keeps_longest_chain_not_concatenation():
    # One relation bundling two disjoint trails (Mailbox old + new) must NOT
    # be summed into one zigzag — that inflated distance/gain ~2-3x. The
    # longest continuous chain wins.
    long_trail = {"geometry": [_g(0.0, 0.0), _g(0.0, 0.1), _g(0.0, 0.2), _g(0.0, 0.3)]}
    short_trail = {"geometry": [_g(5.0, 0.0), _g(5.0, 0.05)]}
    chain = overpass._stitch_route([short_trail, long_trail])
    assert [p.lon for p in chain] == [0.0, 0.1, 0.2, 0.3]


def test_search_trails_sends_identifying_user_agent():
    # OSM policy requires an identifying UA; overpass-api.de answers HTTP 406
    # to Python's default "Python-urllib/3.x" (verified live 2026-07-03), so
    # dropping this header kills search outright.
    seen: list = []

    @contextmanager
    def _open(req, timeout=None):
        seen.append(req.get_header("User-agent"))

        class _Resp:
            def read(self_inner):
                return json.dumps(_OVERPASS).encode("utf-8")

        yield _Resp()

    overpass.search_trails("Mailbox Peak", opener=_open)
    assert seen and seen[0] and "vires" in seen[0]


def test_search_trails_query_uses_body_verbosity():
    # Regression pin: `out tags geom` silently drops relation MEMBERS, so no
    # geometry is ever attached and every candidate fails the >=2-points
    # filter — search returned empty even for trails OSM has (Mailbox Peak
    # Trail, rel 5426108). The mocked-response tests above can't catch this
    # (the fake payload always includes members), so pin the query itself.
    q = overpass._build_query("Mailbox Peak")
    assert "out geom" in q
    assert "out tags" not in q


def test_search_trails_short_query_skips():
    got = overpass.search_trails("ab", opener=_opener_raising)
    assert got.candidates == []
    assert got.provider_ok is True  # never hit the network — not an outage


def test_search_trails_failsoft_returns_empty():
    got = overpass.search_trails("Mailbox Peak", opener=_opener_raising)
    assert got.candidates == []
    assert got.provider_ok is False


def test_search_trails_failsoft_on_readphase_timeout():
    got = overpass.search_trails("Mailbox Peak", opener=_opener_timeout)
    assert got.candidates == []
    assert got.provider_ok is False


def test_search_trails_falls_back_to_mirror():
    # Primary fails, mirror answers — candidates come back with provider_ok.
    calls: list[str] = []

    @contextmanager
    def _open(req, timeout=None):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.URLError("primary busy")

        class _Resp:
            def read(self_inner):
                return json.dumps(_OVERPASS).encode("utf-8")

        yield _Resp()

    got = overpass.search_trails("Mailbox Peak", opener=_open)
    assert got.provider_ok is True
    assert len(got.candidates) == 1
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_search_trails_nonjson_body_falls_through():
    # The public server returns its "too busy" HTML error page with HTTP 200 —
    # must be treated as a provider failure, not raised.
    @contextmanager
    def _open(_req, timeout=None):
        class _Resp:
            def read(self_inner):
                return b"<html>server too busy</html>"

        yield _Resp()

    got = overpass.search_trails("Mailbox Peak", opener=_open)
    assert got.candidates == []
    assert got.provider_ok is False
