"""Initial persistence model for the practice slice (T01).

These are the assignment-side entities the T01-T05 increment needs:
a practice session holding ordered problem instances. Authentication,
pairing, attempts, jobs, and provider tables land in the task that first
uses them; ``PracticeSession.learner_id`` gains its foreign key to the
learner table in T03.
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
