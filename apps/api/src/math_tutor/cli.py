"""Local operator commands.

T01 provides the database gate; T02 adds the interactive adult bootstrap.
Later tasks extend this module further.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy.orm import Session

from math_tutor import auth as auth_service
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


def run_admin() -> int:
    """Interactively create (or reset) the adult administrator.

    The password is read with :func:`getpass.getpass` so it never appears in
    shell history, process arguments, or logs. There is deliberately no
    ``--password`` flag and no unauthenticated web recovery; a local operator
    reruns this command to reset access.
    """

    try:
        settings.session_secret()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    url = settings.database_url()
    try:
        settings.database_path(url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        login_name = input("Administrator login name: ")
    except EOFError, KeyboardInterrupt:
        print("\nerror: administrator bootstrap cancelled.", file=sys.stderr)
        return 1
    try:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
    except EOFError, KeyboardInterrupt:
        print("\nerror: administrator bootstrap cancelled.", file=sys.stderr)
        return 1
    if password != confirm:
        print("error: passwords do not match.", file=sys.stderr)
        return 1

    engine = create_engine_for_url(url)
    try:
        with Session(engine) as db:
            try:
                admin = auth_service.create_or_reset_admin(db, login_name, password)
                db.commit()
                login_label = admin.login_name
            except ValueError as exc:
                db.rollback()
                print(f"error: {exc}", file=sys.stderr)
                return 1
            except Exception as exc:
                db.rollback()
                print(f"error: cannot write administrator record: {exc}", file=sys.stderr)
                print("Run `make migrate` with application writes stopped first.", file=sys.stderr)
                return 1
    finally:
        engine.dispose()

    print(f"Administrator '{login_label}' is ready.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch operator subcommands."""

    parser = argparse.ArgumentParser(prog="math-tutor", description="Math Practice Tutor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("db", help="Validate the SQLite path, runtime, and settings.")
    subparsers.add_parser("admin", help="Interactively create or reset the adult administrator.")
    args = parser.parse_args(argv)
    if args.command == "db":
        return run_db()
    if args.command == "admin":
        return run_admin()
    raise AssertionError(f"Unknown command: {args.command}")  # subparsers require one


if __name__ == "__main__":
    raise SystemExit(main())
