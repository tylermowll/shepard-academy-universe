"""Persistence models for the practice and authentication slices.

T01 added the assignment-side entities (practice sessions holding ordered
problem instances). T02 adds the adult administrator and opaque
device-session entities; pairing, attempts, jobs, and provider tables land
in the task that first uses them. ``PracticeSession.learner_id`` and
``DeviceSession.learner_id`` gain their foreign keys to the learner table
in T03.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from math_tutor.adapters.db.base import Base
from math_tutor.adapters.db.types import UTCDateTime, UUIDType, utcnow

SESSION_STATUSES = ("open", "completed", "skipped")
PROBLEM_STATUSES = ("assigned", "completed", "skipped")


class PracticeSession(Base):
    """One learner's practice run; problems are ordered by position."""

    __tablename__ = "practice_session"
    __table_args__ = (
        CheckConstraint(
            f"status IN {SESSION_STATUSES!r}",
            name="ck_practice_session_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    learner_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    problems: Mapped[list[ProblemInstance]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class ProblemInstance(Base):
    """One assigned problem.

    ``expected_result`` is the hidden answer: it is persisted for deterministic
    verification but must never serialize into a learner-facing payload. The
    public schema in ``math_tutor.api.schemas`` excludes it alongside the raw
    ``parameters`` and ``seed``.
    """

    __tablename__ = "problem_instance"
    __table_args__ = (
        CheckConstraint(
            f"status IN {PROBLEM_STATUSES!r}",
            name="ck_problem_instance_status",
        ),
        CheckConstraint("template_version >= 1", name="ck_problem_instance_template_version"),
        CheckConstraint("position >= 0", name="ck_problem_instance_position"),
        UniqueConstraint("session_id", "position", name="uq_problem_instance_session_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("practice_session.id", ondelete="CASCADE", name="fk_problem_instance_session"),
        nullable=False,
    )
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[int] = mapped_column(nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    problem_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    format_constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="assigned")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    session: Mapped[PracticeSession] = relationship(back_populates="problems")


class Administrator(Base):
    """One adult administrator for the private deployment (T02).

    The password hash is an Argon2id PHC string. It is private persistence
    state: no public schema exposes it.
    """

    __tablename__ = "administrator"
    __table_args__ = (UniqueConstraint("login_name", name="uq_administrator_login_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    login_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    sessions: Mapped[list[DeviceSession]] = relationship(
        back_populates="administrator", cascade="all, delete-orphan", passive_deletes=True
    )


class DeviceSession(Base):
    """One authenticated browser session (T02).

    Only the SHA-256 hash of the opaque cookie token is stored, so a database
    read alone cannot impersonate the holder. ``csrf_token`` is a per-session
    random value echoed back in the ``X-CSRF-Token`` header on state-changing
    requests. ``revoked_at`` marks logout/revocation; ``learner_id`` stays a
    plain identifier until T03 adds the learner table and its foreign key.
    The ``role`` column accepts future learner sessions; T02 creates ``adult``
    rows only and authorizes them accordingly.
    """

    __tablename__ = "device_session"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_device_session_token_hash"),
        CheckConstraint(
            "(role = 'adult' AND administrator_id IS NOT NULL AND learner_id IS NULL) OR "
            "(role = 'learner' AND administrator_id IS NULL AND learner_id IS NOT NULL)",
            name="ck_device_session_principal",
        ),
        CheckConstraint("expires_at > created_at", name="ck_device_session_expiration"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="adult", server_default="adult"
    )
    administrator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("administrator.id", ondelete="CASCADE", name="fk_device_session_administrator"),
        nullable=True,
    )
    learner_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    administrator: Mapped[Administrator | None] = relationship(back_populates="sessions")
