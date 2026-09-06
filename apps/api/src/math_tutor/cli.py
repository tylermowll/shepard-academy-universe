"""Local operator commands. T01 provides the database gate; later tasks extend this."""

from __future__ import annotations

import argparse
import os
import sys

from math_tutor import settings
from math_tutor.adapters.db.engine import create_engine_for_url, verify_connection_settings


def run_db() -> int:
    """Prepare and validate the private SQLite path, runtime, and settings.

    Creates the data directory with restrictive permissions when missing,
    connects with the production connection settings, and verifies the
    embedded SQLite version and effective PRAGMAs. Performs no migration.
    """

    try:
        actual = settings.require_supported_sqlite()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    url = settings.database_url()
    try:
        path = settings.database_path(url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError as exc:
        print(f"error: cannot secure data directory {path.parent}: {exc}", file=sys.stderr)
        return 1

    engine = create_engine_for_url(url)
    try:
        with engine.connect() as connection:
            values = verify_connection_settings(connection)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    floor = ".".join(str(part) for part in settings.MIN_SQLITE_VERSION)
    loaded = ".".join(str(part) for part in actual)
    print(f"database: {path}")
    print(f"sqlite: {loaded} (floor {floor})")
    for name in ("journal_mode", "foreign_keys", "busy_timeout", "synchronous"):
        print(f"{name}: {values[name]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch operator subcommands."""

    parser = argparse.ArgumentParser(prog="math-tutor", description="Math Practice Tutor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("db", help="Validate the SQLite path, runtime, and settings.")
    args = parser.parse_args(argv)
    if args.command == "db":
        return run_db()
    raise AssertionError(f"Unknown command: {args.command}")  # subparsers require one


if __name__ == "__main__":
    raise SystemExit(main())
