"""Explicit local startup: private settings, first-run setup, then foreground services.

Only this operator entry point loads an environment file, using uv's dotenv parser
through captured private pipes. The application settings module never loads files implicitly.
Existing settings and administrator credentials are never replaced on restart.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from math_tutor import cli, container_start, settings
from math_tutor.adapters.db.engine import create_engine_for_url
from math_tutor.adapters.db.models import Administrator

SETUP_TOKEN_ENV = "SHEPARD_SETUP_TOKEN"


def load_environment(destination: Path, root: Path, uv: str) -> dict[str, str]:
    """Parse with uv without exposing warnings containing malformed secret lines."""

    metadata = destination.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise ValueError(
            "The settings file must be a private regular file (permissions 600). "
            "Correct its permissions; startup has not changed its contents."
        )
    if any(character.isspace() for character in destination.name):
        raise ValueError(
            "uv cannot load a settings filename containing whitespace. "
            "Use a filename such as .env; its parent directories may contain spaces."
        )
    environment = os.environ.copy()
    environment.pop("UV_NO_ENV_FILE", None)
    environment.pop("UV_ENV_FILE", None)
    environment.pop(SETUP_TOKEN_ENV, None)
    try:
        loaded = subprocess.run(
            [
                uv,
                "run",
                "--project",
                str(root / "apps/api"),
                "--locked",
                "--no-sync",
                "--offline",
                "--env-file",
                f"./{destination.name}",
                sys.executable,
                "-c",
                "import json, os, sys; json.dump(dict(os.environ), sys.stdout)",
            ],
            cwd=destination.parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Timed out loading private settings; no services were started.") from None
    # uv may warn about a malformed line and still exit successfully. Reject the
    # entire result, and never print either captured pipe (they may contain secrets).
    if loaded.returncode or loaded.stderr.strip():
        raise ValueError(
            "Cannot load private settings. Check the file's KEY=value syntax locally "
            "and your uv installation. Parser diagnostics were hidden because they "
            "may include secrets. No services were started."
        )
    try:
        values = json.loads(loaded.stdout)
    except ValueError:
        raise ValueError("Cannot read the private settings loader result.") from None
    if not isinstance(values, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()
    ):
        raise ValueError("Invalid private settings loader result.")
    return dict(values)


def validate_origin(*, gateway: bool, loopback: bool) -> SplitResult:
    """Fail before builds, database setup, or password prompts on bad settings."""

    settings.session_secret()
    settings.require_supported_sqlite()
    settings.database_path()
    origin = urlsplit(settings.app_public_origin())
    if gateway and origin.scheme != "https":
        raise ValueError(
            "make serve requires APP_PUBLIC_ORIGIN=https://your-phone-reachable-hostname "
            "(see docs/PHONE_SETUP.md)."
        )
    if loopback and origin.scheme != "http":
        raise ValueError("For HTTPS use make start or make serve; make dev is loopback only.")
    return origin


@contextmanager
def native_lock(database: Path) -> Iterator[None]:
    """Allow one native launcher per database; release automatically after crashes."""

    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        database.parent / f".{database.name}.native.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "This database already has a running native app. "
                "Use its browser address, or stop it with Ctrl+C before restarting."
            ) from None
        yield
    finally:
        os.close(descriptor)


def check_port(origin: SplitResult) -> None:
    """Catch another API using the requested listener before setup or builds."""

    host = "127.0.0.1" if origin.scheme == "https" else origin.hostname
    port = 8000 if origin.scheme == "https" else origin.port or 80
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host or "127.0.0.1", port))
        except OSError:
            raise ValueError(
                f"Cannot use local port {port}. Stop the app already using it, "
                "or choose a different loopback APP_PUBLIC_ORIGIN port."
            ) from None


def prepare_database(root: Path) -> None:
    """Initialize an empty database only; retained databases need explicit upgrades."""

    config = Config(str(root / "apps/api/alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url().replace("%", "%%"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_engine_for_url(settings.database_url())
    try:
        with engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    if not tables:
        print("Initializing your private database.", flush=True)
        command.upgrade(config, "head")
    elif current != heads:
        raise ValueError(
            "The existing database needs a reviewed migration. Stop all API and worker "
            "processes, back up retained data, run `make migrate`, then `make start`. "
            "Startup has not migrated or deleted your existing data."
        )


def start_services(root: Path, origin: SplitResult, make: str) -> int:
    """Hold the native lock while bootstrapping, building, and supervising services."""

    os.environ.pop(SETUP_TOKEN_ENV, None)
    checked = subprocess.run([make, "toolchain-check"], cwd=root, check=False)
    if checked.returncode:
        return checked.returncode
    with native_lock(settings.database_path()):
        check_port(origin)
        prepare_database(root)
        token = owner_setup_token(origin)
        print("Building the app…", flush=True)
        built = subprocess.run([make, "build"], cwd=root, check=False)
        if built.returncode:
            print("Build failed; services were not started. Run `make bootstrap` if needed.")
            return built.returncode
        arguments = [sys.executable, str(root / "scripts/dev.py")]
        if origin.scheme == "https":
            arguments.append("--gateway")
        environment = os.environ.copy()
        if token:
            environment[SETUP_TOKEN_ENV] = token
            print(
                "Create your adult account in the browser. This private owner link "
                "works once and expires in 30 minutes; do not share it:",
                flush=True,
            )
            print(f"{origin.geturl()}/#setup={token}", flush=True)
        return subprocess.run(arguments, cwd=root, env=environment, check=False).returncode


def owner_setup_token(origin: SplitResult) -> str | None:
    """Prepare one owner claim; never modify an administrator or store a token."""

    engine = create_engine_for_url(settings.database_url())
    try:
        with Session(engine) as db:
            claimed = db.scalar(select(Administrator.id).limit(1)) is not None
            if (
                origin.scheme == "https"
                and db.scalar(
                    select(Administrator.id)
                    .where(Administrator.local_only_password.is_(True))
                    .limit(1)
                )
                is not None
            ):
                raise ValueError(
                    "An administrator has a computer-only password. Before enabling HTTPS "
                    "or phone access, run `make admin` and replace that account's password "
                    "with at least 12 characters. No credentials have been changed."
                )
    finally:
        engine.dispose()
    if not claimed and os.getenv("APP_MODE", "private") != "demo":
        return secrets.token_urlsafe(32)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--make", default="make")
    parser.add_argument(
        "--command",
        choices=["start", "db", "migrate", "admin", "worker", "backup", "restore"],
        default="start",
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--writes-stopped", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--gateway", action="store_true")
    modes.add_argument("--loopback", action="store_true")
    args = parser.parse_args(argv)
    if args.command in {"backup", "restore"}:
        if not args.output or not args.writes_stopped:
            parser.error("Backup/restore require --output and --writes-stopped.")
        if args.command == "restore" and (not args.input or not args.ledger):
            parser.error("Restore requires --input and the current --ledger.")
    root = settings.repository_root()
    destination = (args.env_file or root / ".env").absolute()
    try:
        # Docker already owns the configured installation. Ask that API for a
        # fresh owner link before reading native settings, checking Node, or
        # touching a second database. Explicit alternate env files stay native.
        if (
            args.command == "start"
            and not args.loopback
            and not args.gateway
            and destination == root / ".env"
            and (container := container_start.running_api()) is not None
        ):
            return container_start.connect(container)
        os.environ.pop(SETUP_TOKEN_ENV, None)
        if args.command == "start" and not destination.exists() and cli.run_setup(destination):
            return 1
        if destination.exists():
            os.environ.update(load_environment(destination, root, args.uv))
        # The settings are already loaded; later uv build commands must not
        # reopen a private file or print an unredacted dotenv diagnostic.
        os.environ.pop("UV_ENV_FILE", None)
        os.environ.pop("UV_NO_ENV_FILE", None)
        os.environ.pop(SETUP_TOKEN_ENV, None)
        if args.command == "db":
            return cli.run_db()
        if args.command == "admin":
            return cli.run_admin()
        if args.command == "migrate":
            with native_lock(settings.database_path()):
                config = Config(str(root / "apps/api/alembic.ini"))
                command.upgrade(config, "head")
            return 0
        if args.command == "worker":
            settings.session_secret()
            return subprocess.run(
                [sys.executable, "-m", "math_tutor.worker"], cwd=root, check=False
            ).returncode
        if args.command in {"backup", "restore"}:
            arguments = [
                sys.executable,
                "-m",
                "math_tutor.backup",
                args.command,
                str(args.output if args.command == "backup" else args.input),
                "--writes-stopped",
            ]
            if args.command == "restore":
                arguments.extend(
                    ["--destination", str(args.output), "--deletion-ledger", str(args.ledger)]
                )
            with native_lock(settings.database_path()):
                return subprocess.run(
                    arguments, cwd=root, env=os.environ.copy(), check=False
                ).returncode
        origin = validate_origin(gateway=args.gateway, loopback=args.loopback)
        return start_services(root, origin, args.make)
    except ValueError as exc:
        print(f"Startup stopped: {exc}", file=sys.stderr)
        print(
            "Check your private settings locally; never paste secrets into chat.", file=sys.stderr
        )
        return 1
    except OSError, SQLAlchemyError, RuntimeError:
        print(
            "Startup stopped: cannot prepare local services. Check database/settings "
            "permissions and installed tools. No credentials have been reset.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Restart with `make start`; saved work and your login are kept.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
