"""Server-side recurrence expansion for the athletic calendar (vires-ops#31).

``CalendarEvent.recurrence='weekly'`` events are stored as ONE row (the series,
anchored at ``event_date``) — never fanned out into materialized occurrence
rows. Concrete occurrences within a date window (e.g. the coach's lookahead)
are computed here, on read.
"""

from __future__ import annotations

from datetime import date, timedelta

from api.db.models import CalendarEvent

_WEEK = timedelta(days=7)


def expand_occurrences(
    event: CalendarEvent, window_start: date, window_end: date
) -> list[tuple[date, date | None]]:
    """Concrete (occurrence_date, occurrence_end_date) pairs for ``event`` that
    fall within ``[window_start, window_end]`` (inclusive).

    - ``recurrence='none'``: at most one occurrence — the event's own span,
      clipped to whether its span intersects the window at all (an event either
      falls in the window or it doesn't; unlike a multi-day objective band, we
      don't clip the span itself, since the caller wants the whole event).
    - ``recurrence='weekly'``: every 7 days from ``event_date``, each occurrence
      landing inside the window. Multi-day spans aren't supported for recurring
      events (event_end_date is ignored for the series; each occurrence is a
      single day at the top of the cadence).
    """
    if window_end < window_start:
        return []

    if event.recurrence == "weekly":
        if event.event_date > window_end:
            return []
        # Advance from event_date to the first occurrence >= window_start,
        # in whole-week steps (never using a per-day loop over the whole gap).
        if event.event_date >= window_start:
            first = event.event_date
        else:
            gap_days = (window_start - event.event_date).days
            weeks_needed = -(-gap_days // 7)  # ceil div
            first = event.event_date + _WEEK * weeks_needed
        occurrences: list[tuple[date, date | None]] = []
        current = first
        while current <= window_end:
            occurrences.append((current, None))
            current += _WEEK
        return occurrences

    # recurrence == 'none': a single occurrence, in-window if its span
    # (event_date..event_end_date or just event_date) intersects the window.
    span_end = event.event_end_date or event.event_date
    if span_end < window_start or event.event_date > window_end:
        return []
    return [(event.event_date, event.event_end_date)]
