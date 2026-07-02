"""Parse a GPX file into route points — stdlib only, no new dependency.

GPX is simple XML; we want trackpoints/routepoints with lat/lon and (usually
embedded) elevation. Parsed namespace-robustly so GPX 1.0 and 1.1, and both
``<trkpt>`` tracks and ``<rtept>`` routes, work without pinning a namespace.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from api.services.geo.measure import GeoPoint


def _localname(tag: str) -> str:
    # ElementTree renders namespaced tags as "{uri}local"; take the local part.
    return tag.rsplit("}", 1)[-1]


class GpxParseError(ValueError):
    """Raised when the uploaded file isn't valid GPX or has no usable points."""


@dataclass
class GpxTrack:
    points: list[GeoPoint]
    # Elapsed time from the first to last timestamped point (seconds), if the GPX
    # carries <time> — so a GPX import fills distance + elevation + duration and
    # leaves only pack weight to enter. None when the track is untimed.
    duration_s: int | None


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_gpx(data: bytes | str) -> GpxTrack:
    """Parse a GPX document into ordered points + elapsed duration.

    Raises :class:`GpxParseError` on malformed XML or when fewer than 2 usable
    trackpoints/routepoints are present — the caller surfaces that as a 422, not a
    silent empty route.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise GpxParseError(f"not valid GPX/XML: {e}") from e

    points: list[GeoPoint] = []
    times: list[datetime] = []
    for el in root.iter():
        if _localname(el.tag) not in ("trkpt", "rtept"):
            continue
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        ele: float | None = None
        t: datetime | None = None
        for child in el:
            ln = _localname(child.tag)
            if ln == "ele" and child.text:
                try:
                    ele = float(child.text)
                except ValueError:
                    ele = None
            elif ln == "time":
                t = _parse_time(child.text)
        try:
            points.append(GeoPoint(lat=float(lat), lon=float(lon), ele_m=ele))
        except ValueError:
            continue
        if t is not None:
            times.append(t)

    if len(points) < 2:
        raise GpxParseError("GPX contained fewer than 2 usable track points")

    duration_s: int | None = None
    if len(times) >= 2:
        secs = (max(times) - min(times)).total_seconds()
        duration_s = int(secs) if secs > 0 else None
    return GpxTrack(points=points, duration_s=duration_s)
