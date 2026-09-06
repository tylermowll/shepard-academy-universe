"""Declarative base with a stable constraint-naming convention."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all persistence models.

    Named constraints keep Alembic migrations and SQLite table rebuilds
    deterministic (see D004).
    """

    __abstract__ = True


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

Base.metadata.naming_convention = NAMING_CONVENTION
