"""GPX parsing — namespace-robust, with duration from timestamps."""

from __future__ import annotations

import pytest

from api.services.geo.gpx import GpxParseError, parse_gpx

_GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test Ruck</name><trkseg>
    <trkpt lat="47.60" lon="-122.33"><ele>50</ele><time>2026-07-01T15:00:00Z</time></trkpt>
    <trkpt lat="47.61" lon="-122.33"><ele>150</ele><time>2026-07-01T15:30:00Z</time></trkpt>
    <trkpt lat="47.62" lon="-122.33"><ele>300</ele><time>2026-07-01T16:00:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def test_parse_points_elevation_and_duration():
    track = parse_gpx(_GPX)
    assert len(track.points) == 3
    assert track.points[0].ele_m == 50.0
    assert track.points[-1].ele_m == 300.0
    assert track.duration_s == 3600  # 15:00 → 16:00


def test_parse_untimed_gpx_has_no_duration():
    gpx = _GPX.replace("<time>2026-07-01T15:00:00Z</time>", "").replace(
        "<time>2026-07-01T15:30:00Z</time>", ""
    ).replace("<time>2026-07-01T16:00:00Z</time>", "")
    track = parse_gpx(gpx)
    assert track.duration_s is None
    assert len(track.points) == 3


def test_parse_rejects_malformed_xml():
    with pytest.raises(GpxParseError):
        parse_gpx("not xml at all <<<")


def test_parse_rejects_too_few_points():
    gpx = """<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
      <trkpt lat="47.6" lon="-122.3"><ele>50</ele></trkpt>
    </trkseg></trk></gpx>"""
    with pytest.raises(GpxParseError):
        parse_gpx(gpx)


def test_parse_accepts_bytes():
    track = parse_gpx(_GPX.encode("utf-8"))
    assert len(track.points) == 3


def test_parse_rejects_entity_expansion_bomb():
    # "Billion laughs" — stdlib ElementTree has no protection against this;
    # defusedxml rejects it before expansion (CodeQL py/xml-bomb, config#2632).
    bomb = """<?xml version="1.0"?>
    <!DOCTYPE gpx [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
      <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
    ]>
    <gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
      <trkpt lat="47.6" lon="-122.3"><name>&lol3;</name></trkpt>
    </trkseg></trk></gpx>"""
    with pytest.raises(GpxParseError):
        parse_gpx(bomb)
