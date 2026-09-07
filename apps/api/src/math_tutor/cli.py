"""Local operator commands.

T01 provides the database gate; T02 adds the interactive adult bootstrap.
Later tasks extend this module further.
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import shlex
import sys
import warnings
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from math_tutor import auth as auth_service
from math_tutor import settings
from math_tutor.adapters.db.engine import create_engine_for_url, verify_connection_settings
from math_tutor.adapters.db.models import Administrator


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

    try:
        url = settings.database_url()
        path = settings.database_path(url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    engine = create_engine_for_url(url)
    try:
        with engine.connect() as connection:
            values = verify_connection_settings(connection)
    except RuntimeError, SQLAlchemyError, OSError:
        print("error: cannot prepare database; check its path and permissions.", file=sys.stderr)
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


def run_setup(destination: Path) -> int:
    """Generate a private shell-compatible environment file without reading one."""

    values = {
        settings.DATABASE_URL_ENV_VAR: f"sqlite+pysqlite:///{settings.database_path()}",
        settings.SESSION_SECRET_ENV_VAR: secrets.token_urlsafe(48),
        settings.APP_PUBLIC_ORIGIN_ENV_VAR: settings.app_public_origin(),
    }
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            for name, value in values.items():
                output.write(f"{name}={shlex.quote(value)}\n")
    except FileExistsError:
        print(
            "error: settings file already exists; refusing to read or overwrite it.",
            file=sys.stderr,
        )
        return 1
    except OSError:
        print(
            "error: cannot create settings file; check its directory permissions.", file=sys.stderr
        )
        return 1
    print(f"Created private settings at {destination}. Run `make start` to continue.")
    return 0


def run_admin(*, only_if_missing: bool = False) -> int:
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

    if only_if_missing:
        engine = create_engine_for_url(url)
        try:
            with Session(engine) as db:
                if db.scalar(select(Administrator.id).limit(1)) is not None:
                    print("Administrator already set up; keeping the existing login.")
                    return 0
        except SQLAlchemyError, OSError:
            print(
                "error: cannot check administrator setup; run `make migrate` first.",
                file=sys.stderr,
            )
            return 1
        finally:
            engine.dispose()
        print(
            "Create your adult administrator login. This account can also have a learner profile."
        )

    try:
        login_name = input("Administrator login name: ")
    except EOFError, KeyboardInterrupt:
        print("\nerror: administrator bootstrap cancelled.", file=sys.stderr)
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("New password: ")
            confirm = getpass.getpass("Confirm password: ")
    except getpass.GetPassWarning:
        print("error: a terminal with hidden password input is required.", file=sys.stderr)
        return 1
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
                if only_if_missing:
                    db.connection(execution_options={"sqlite_begin_immediate": True})
                    if db.scalar(select(Administrator.id).limit(1)) is not None:
                        print("Administrator was already created; keeping the existing login.")
                        return 0
                admin = auth_service.create_or_reset_admin(db, login_name, password)
                db.commit()
                login_label = admin.login_name
            except ValueError as exc:
                db.rollback()
                print(f"error: {exc}", file=sys.stderr)
                return 1
            except SQLAlchemyError, OSError:
                db.rollback()
                print("error: cannot write administrator record.", file=sys.stderr)
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
    setup = subparsers.add_parser("setup", help="Generate a private local environment file.")
    setup.add_argument("--output", type=Path, help="New file path; existing files are never read.")
    args = parser.parse_args(argv)
    if args.command == "db":
        return run_db()
    if args.command == "admin":
        return run_admin()
    if args.command == "setup":
        return run_setup(args.output or settings.repository_root() / ".env")
    raise AssertionError(f"Unknown command: {args.command}")  # subparsers require one


if __name__ == "__main__":
    raise SystemExit(main())
