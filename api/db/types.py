"""Custom SQLAlchemy column types."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Always hand the app tz-aware UTC datetimes.

    SQLite stores datetimes as strings and drops tzinfo, so a value read back is
    naive — which serializes to JSON without an offset and gets misread by clients
    as *local* time (this broke the workout "elapsed" timer). This decorator stores
    naive-UTC and re-attaches UTC on load, so the API always emits an explicit
    offset.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
