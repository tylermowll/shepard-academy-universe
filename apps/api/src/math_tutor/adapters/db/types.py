"""Persistence column types shared by every SQLite table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class UUIDType(TypeDecorator[uuid.UUID]):
    """Store UUIDs consistently as 36-character text (see SPEC section 9)."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: uuid.UUID | str | None, dialect: Dialect) -> Any:
        # Returns storage text for the String impl; Any marks that handoff.
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"Invalid UUID value: {value!r}") from exc

    def process_result_value(self, value: object | None, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(str(value))


class UTCDateTime(TypeDecorator[datetime]):
    """Normalize timestamps to aware UTC values; reject naive input.

    SQLite stores datetimes without zone information, so the result processor
    reattaches UTC explicitly. Naive datetimes are refused on write instead of
    being silently interpreted as UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Naive datetimes are rejected; pass an aware UTC value.")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):  # pragma: no cover - driver contract
            raise ValueError(f"Invalid datetime value: {value!r}")
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    """Return the current aware UTC time for column defaults."""

    return datetime.now(UTC)
