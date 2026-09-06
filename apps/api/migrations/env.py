"""Alembic environment: migrate the configured SQLite file with app settings.

The target URL is resolved by ``math_tutor.settings`` so migrations, the API,
the worker, and ``make db`` always address the same file. SQLite DDL runs
inside a transaction, so a failed migration rolls back instead of leaving a
half-applied schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_tutor import settings  # noqa: E402
from math_tutor.adapters.db import models  # noqa: E402,F401  (register table metadata)
from math_tutor.adapters.db.base import Base  # noqa: E402
from math_tutor.adapters.db.engine import create_engine_for_url  # noqa: E402

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Use an explicit Alembic URL when provided, else the app settings."""

    override = config.get_main_option("sqlalchemy.url")
    if override:
        return override
    return settings.database_url()


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured on-disk database."""

    engine = create_engine_for_url(database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
