"""SQLite engine factory with the production connection contract (D004).

Every connection enables WAL journaling, foreign-key enforcement, a bounded
5-second lock wait, and full synchronous durability. PRAGMAs are applied in a
``connect`` listener, which SQLAlchemy invokes outside any transaction.

Transaction control is explicit: callers use ``Session``/``engine.begin()``
blocks and commit or roll back deliberately. The pysqlite driver's legacy
implicit transaction behavior is never relied upon; commit/rollback semantics
are covered by integration tests against temporary on-disk databases.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

from math_tutor import settings

#: PRAGMA name -> (expected effective value, setter SQL).
CONNECTION_PRAGMAS: tuple[tuple[str, str, str], ...] = (
    ("journal_mode", "wal", "PRAGMA journal_mode=WAL"),
    ("foreign_keys", "1", "PRAGMA foreign_keys=ON"),
    ("busy_timeout", "5000", "PRAGMA busy_timeout=5000"),
    ("synchronous", "FULL", "PRAGMA synchronous=FULL"),
)


def _apply_connection_settings(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for _name, _expected, setter in CONNECTION_PRAGMAS:
            cursor.execute(setter)
    finally:
        cursor.close()


def create_engine_for_url(url: str) -> Engine:
    """Create an engine whose every connection carries the D004 settings."""

    engine = create_engine(url)
    event.listen(engine, "connect", _apply_connection_settings)
    return engine


def create_default_engine() -> Engine:
    """Create an engine for the configured database URL."""

    return create_engine_for_url(settings.database_url())


_SYNCHRONOUS_NAMES = {"0": "OFF", "1": "NORMAL", "2": "FULL", "3": "EXTRA"}


def effective_settings(connection: Connection) -> dict[str, str]:
    """Read back the effective PRAGMA values on an open connection.

    SQLite reports ``synchronous`` numerically (2 means FULL); normalize it
    to the symbolic name so the D004 contract reads the same everywhere.
    """

    values: dict[str, str] = {}
    for name, _expected, _setter in CONNECTION_PRAGMAS:
        raw = str(connection.exec_driver_sql(f"PRAGMA {name}").scalar())
        values[name] = _SYNCHRONOUS_NAMES.get(raw, raw) if name == "synchronous" else raw
    return values


def verify_connection_settings(connection: Connection) -> dict[str, str]:
    """Assert the D004 connection contract; return the effective values."""

    values = effective_settings(connection)
    mismatches = [
        f"{name}={values[name]!r} (expected {expected!r})"
        for name, expected, _setter in CONNECTION_PRAGMAS
        if values[name] != expected
    ]
    if mismatches:
        raise RuntimeError(
            "SQLite connection settings mismatch (see D004): " + "; ".join(mismatches)
        )
    return values
