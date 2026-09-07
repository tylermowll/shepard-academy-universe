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

import os
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Connection, Engine

from math_tutor import settings

#: PRAGMA name -> (expected effective value, setter SQL).
CONNECTION_PRAGMAS: tuple[tuple[str, str, str], ...] = (
    ("journal_mode", "wal", "PRAGMA journal_mode=WAL"),
    ("foreign_keys", "1", "PRAGMA foreign_keys=ON"),
    ("busy_timeout", "5000", "PRAGMA busy_timeout=5000"),
    ("synchronous", "FULL", "PRAGMA synchronous=FULL"),
)


def _apply_connection_settings(dbapi_connection: Any, _record: Any) -> None:
    # Disable sqlite3's implicit BEGIN. SQLAlchemy's begin event below owns
    # transactions, including SELECT, DDL, and outer savepoint rollback.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    try:
        for _name, _expected, setter in CONNECTION_PRAGMAS:
            cursor.execute(setter)
        for name, expected, _setter in CONNECTION_PRAGMAS:
            raw = str(cursor.execute(f"PRAGMA {name}").fetchone()[0])
            actual = _SYNCHRONOUS_NAMES.get(raw, raw) if name == "synchronous" else raw
            if actual != expected:
                raise RuntimeError(f"SQLite connection setting {name} does not match D004.")
    finally:
        cursor.close()


def _begin_transaction(connection: Connection) -> None:
    immediate = connection.get_execution_options().get("sqlite_begin_immediate", False)
    connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")


def _prepare_private_file(path: Path) -> None:
    """Create private storage before SQLite can create world-readable files."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.chmod(0o600)


def create_engine_for_url(url: str) -> Engine:
    """Create an engine whose every connection carries the D004 settings."""

    settings.require_supported_sqlite()
    path = settings.database_path(url)

    def connect() -> sqlite3.Connection:
        _prepare_private_file(path)
        return sqlite3.connect(path, check_same_thread=False, timeout=5.0)

    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        creator=connect,
        hide_parameters=True,
    )
    event.listen(engine, "connect", _apply_connection_settings)
    event.listen(engine, "begin", _begin_transaction)
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
