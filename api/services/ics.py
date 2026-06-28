"""Minimal iCalendar (RFC 5545) builder — no deps.

Emits a VCALENDAR of all-day VEVENTs so the Vires calendar can be **subscribed to**
from Google/Apple Calendar (read-only overlay). Pure + testable: callers pass plain
``IcsEvent`` data; this module only does formatting (escaping, line folding, CRLF).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class IcsEvent:
    uid: str
    start: date  # all-day
    summary: str
    description: str
    dtstamp: datetime


def _esc(text: str) -> str:
    """Escape a TEXT value per RFC 5545 (order matters: backslash first)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Fold a content line to <=75 octets; continuation lines start with a space."""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    out: list[str] = []
    cur = ""
    for ch in line:
        # leave headroom so a continuation's leading space still fits
        if len((cur + ch).encode("utf-8")) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _vevent(e: IcsEvent) -> list[str]:
    return [
        "BEGIN:VEVENT",
        f"UID:{e.uid}",
        f"DTSTAMP:{_stamp(e.dtstamp)}",
        f"DTSTART;VALUE=DATE:{e.start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(e.start + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_esc(e.summary)}",
        f"DESCRIPTION:{_esc(e.description)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def build_calendar(name: str, events: list[IcsEvent]) -> str:
    logical = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nous Ergon//Vires//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"NAME:{_esc(name)}",
        f"X-WR-CALNAME:{_esc(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for e in events:
        logical += _vevent(e)
    logical.append("END:VCALENDAR")

    physical: list[str] = []
    for line in logical:
        physical += _fold(line)
    return "\r\n".join(physical) + "\r\n"
