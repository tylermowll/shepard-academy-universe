"""Local configuration for the Math Practice Tutor.

T01 owns the database-path portion of the configuration contract; T02 owns
the session-secret and public-origin portion. Provider settings belong to
later tasks. This module resolves exactly one absolute on-disk SQLite path
so the API, worker, migrations, and commands agree regardless of working
directory when an absolute ``DATABASE_URL`` is set.

Only SQLite is supported (see D004). Any other database scheme is rejected
rather than silently mapped to a second engine.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "math_tutor.sqlite3"
DATA_DIR_ENV_VAR = "MATH_TUTOR_DATA_DIR"
DATABASE_URL_ENV_VAR = "DATABASE_URL"
SESSION_SECRET_ENV_VAR = "SESSION_SECRET"
APP_PUBLIC_ORIGIN_ENV_VAR = "APP_PUBLIC_ORIGIN"

DEFAULT_PUBLIC_ORIGIN = "http://localhost:8080"

#: Session secrets must be operator-generated randomness, not a committed
#: placeholder. Values in this set (compared case-insensitively after
#: stripping) and anything shorter than the minimum are rejected wherever
#: authentication runs, so startup with an unconfigured secret fails loudly
#: instead of signing sessions with a guessable key.
PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "generate_at_setup",
        "changeme",
        "change_me",
        "placeholder",
        "secret",
        "password",
        "test",
    }
)
MIN_SESSION_SECRET_LENGTH = 32

#: Lowest embedded SQLite accepted by setup and CI. Python 3.14.7 loads 3.53.1
#: while current stable is 3.53.4; the justified exception is recorded under
#: D001 and must be rechecked on the next tooling update.
MIN_SQLITE_VERSION = (3, 53, 1)

_SQLITE_SCHEMES = frozenset({"sqlite", "sqlite+pysqlite"})


def data_dir() -> Path:
    """Return the private local data directory (created on demand by ``make db``)."""

    configured = os.environ.get(DATA_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "data"


def default_database_url() -> str:
    """Return the development database URL under the private data directory."""

    return f"sqlite+pysqlite:///{data_dir() / DEFAULT_DB_FILENAME}"


def database_url() -> str:
    """Return the configured database URL, or the development default."""

    return os.environ.get(DATABASE_URL_ENV_VAR, default_database_url())


def database_path(url: str | None = None) -> Path:
    """Resolve a SQLite URL to one absolute on-disk database path.

    Relative paths resolve under :func:`data_dir`. Non-SQLite schemes raise
    ``ValueError`` so a misconfigured URL fails loudly instead of selecting a
    different engine.
    """

    from sqlalchemy.engine.url import make_url

    raw = url if url is not None else database_url()
    parsed = make_url(raw)
    if parsed.drivername not in _SQLITE_SCHEMES:
        raise ValueError(
            f"Unsupported database scheme {parsed.drivername!r}: "
            "this application supports only local SQLite (see D004)."
        )
    name = parsed.database
    if not name or name == ":memory:":
        raise ValueError("A file-backed SQLite database path is required.")
    # Strip the leading slash form that absolute sqlite URLs produce, e.g.
    # sqlite+pysqlite:////app/data/app.db -> path //app/data/app.db.
    candidate = Path(name[1:] if name.startswith("//") else name)
    if not candidate.is_absolute():
        candidate = data_dir() / candidate
    return candidate.absolute()


def session_secret() -> str:
    """Return the configured session secret, rejecting placeholders.

    Raises ``ValueError`` when the secret is missing, matches a known
    placeholder, or is shorter than :data:`MIN_SESSION_SECRET_LENGTH`.
    Authentication endpoints and the admin CLI call this before touching
    credentials or sessions; the liveness probe stays exempt.
    """

    raw = os.environ.get(SESSION_SECRET_ENV_VAR, "")
    if raw.strip().lower() in PLACEHOLDER_SECRETS or len(raw) < MIN_SESSION_SECRET_LENGTH:
        raise ValueError(
            f"{SESSION_SECRET_ENV_VAR} is missing or a placeholder: generate a random "
            f"secret of at least {MIN_SESSION_SECRET_LENGTH} characters (see .env.example). "
            "Startup with an unconfigured secret is rejected."
        )
    return raw


def app_public_origin() -> str:
    """Return the configured same-origin public address for cookie/Origin checks."""

    return os.environ.get(APP_PUBLIC_ORIGIN_ENV_VAR, DEFAULT_PUBLIC_ORIGIN)


def sqlite_version() -> tuple[int, int, int]:
    """Return the SQLite library version actually loaded by this Python."""

    parts = sqlite3.sqlite_version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def require_supported_sqlite() -> tuple[int, int, int]:
    """Return the loaded SQLite version, or raise if it is below the floor."""

    actual = sqlite_version()
    if actual < MIN_SQLITE_VERSION:
        floor = ".".join(str(part) for part in MIN_SQLITE_VERSION)
        found = ".".join(str(part) for part in actual)
        raise RuntimeError(
            f"Embedded SQLite {found} is below the supported floor {floor} "
            "(see D001/D004). Upgrade the Python runtime."
        )
    return actual
