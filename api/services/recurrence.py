"""Server-side recurrence expansion for a recurring activity (formerly the
athletic-calendar CalendarEvent, vires-ops#31 — merged into
``activity_details``, see ``api.db.models.ActivityDetail``).

A ``recurrence='weekly'`` activity is stored as ONE row (the series, anchored
at its own ``WorkoutSession.started_at`` date) — never fanned out into
materialized occurrence rows. Concrete occurrences within a date window
(e.g. the coach's lookahead, or the ``/plan/calendar`` feed) are computed
here, on read. Tapping into a specific occurrence materializes it into its
own linked row (``WorkoutSession.recurrence_source_id``) — see
``api.routers.workouts.materialize_occurrence`` — but that's a separate,
explicit step; this module never persists anything.

Pure primitives, no ORM dependency — kept trivially unit-testable and free
of any import of ``api.db.models``.
"""

from __future__ import annotations

from datetime import date, timedelta

_WEEK = timedelta(days=7)


def expand_occurrences(
    anchor_date: date,
    span_end_date: date | None,
    recurrence: str,
    window_start: date,
    window_end: date,
) -> list[tuple[date, date | None]]:
    """Concrete (occurrence_date, occurrence_end_date) pairs that fall within
    ``[window_start, window_end]`` (inclusive).

    - ``recurrence='none'``: at most one occurrence — the activity's own
      span, clipped to whether its span intersects the window at all (an
      activity either falls in the window or it doesn't; unlike a multi-day
      objective band, we don't clip the span itself, since the caller wants
      the whole activity).
    - ``recurrence='weekly'``: every 7 days from ``anchor_date``, each
      occurrence landing inside the window. Multi-day spans aren't supported
      for a recurring series (``span_end_date`` is ignored; each occurrence
      is a single day at the top of the cadence).
    """
    if window_end < window_start:
        return []

    if recurrence == "weekly":
        if anchor_date > window_end:
            return []
        # Advance from anchor_date to the first occurrence >= window_start,
        # in whole-week steps (never using a per-day loop over the whole gap).
        if anchor_date >= window_start:
            first = anchor_date
        else:
            gap_days = (window_start - anchor_date).days
            weeks_needed = -(-gap_days // 7)  # ceil div
            first = anchor_date + _WEEK * weeks_needed
        occurrences: list[tuple[date, date | None]] = []
        current = first
        while current <= window_end:
            occurrences.append((current, None))
            current += _WEEK
        return occurrences

    # recurrence == 'none': a single occurrence, in-window if its span
    # (anchor_date..span_end_date or just anchor_date) intersects the window.
    span_end = span_end_date or anchor_date
    if span_end < window_start or anchor_date > window_end:
        return []
    return [(anchor_date, span_end_date)]
