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


DEFAULT_PROFILE = {
    "name": "Guided practice",
    "topics": ["fractions.add"],
    "difficulty": "standard",
    "solution_policy": "after_two_attempts",
    "session_problem_limit": 5,
    "teaching_style": "guided",
    "verbosity": "standard",
    "language": "en",
    "custom_instructions": "",
}


class PracticeSession(Base):
    """One learner's practice run; problems are ordered by position."""

    __tablename__ = "practice_session"
    __table_args__ = (
        CheckConstraint(
            f"status IN {SESSION_STATUSES!r}",
            name="ck_practice_session_status",
        ),
        UniqueConstraint("learner_id", "request_key", name="uq_session_request"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("learner.id", ondelete="CASCADE", name="fk_practice_session_learner"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    request_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default=lambda: str(uuid.uuid4())
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    profile_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("tutor_profile_version.id")
    )
    profile_settings: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: dict(DEFAULT_PROFILE)
    )
    mode: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("mode IN ('built_in', 'ai_tutor')", name="ck_session_mode"),
        nullable=False,
        default="built_in",
        server_default="built_in",
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    initiative: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint(
            "initiative IN ('tutor_led', 'balanced', 'learner_led')", name="ck_session_initiative"
        ),
        nullable=False,
        default="balanced",
        server_default="balanced",
    )

    learner: Mapped[Learner] = relationship()

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

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    assistance_level: Mapped[int] = mapped_column(nullable=False, default=0)
    request_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default=lambda: str(uuid.uuid4())
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
    local_only_password: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="0"
    )
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
    learner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("learner.id", ondelete="CASCADE", name="fk_device_session_learner"),
        nullable=True,
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    administrator: Mapped[Administrator | None] = relationship(back_populates="sessions")


class Learner(Base):
    __tablename__ = "learner"
    __table_args__ = (
        CheckConstraint(
            "eligibility IN ('adult', 'minor', 'unknown')", name="ck_learner_eligibility"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    eligibility: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class PairingRequest(Base):
    __tablename__ = "pairing_request"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_pairing_expiration"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    learner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("learner.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Submission(Base):
    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint("learner_id", "request_key", name="uq_submission_request"),
        CheckConstraint("kind IN ('answer', 'question', 'hint')", name="ck_submission_kind"),
        CheckConstraint(
            "status IN ('queued', 'checking', 'tutoring', 'interpreting', 'awaiting_confirmation', 'completed', 'failed', 'canceled')",
            name="ck_submission_status",
        ),
        CheckConstraint("help_level BETWEEN 0 AND 4", name="ck_submission_help"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("learner.id", ondelete="CASCADE"), nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("problem_instance.id", ondelete="CASCADE"), nullable=False
    )
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    work_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    help_level: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    safe_error: Mapped[str | None] = mapped_column(String(256))
    assignment_version: Mapped[int] = mapped_column(nullable=False, default=1)
    image_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class PhoneUpload(Base):
    """One short-lived delegated photo permission; no bearer secret is persisted."""

    __tablename__ = "phone_upload"
    __table_args__ = (
        UniqueConstraint("issuer_id", "request_key", name="uq_phone_upload_request"),
        CheckConstraint("version >= 1", name="ck_phone_upload_version"),
        CheckConstraint("expires_at > created_at", name="ck_phone_upload_expiration"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("device_session.id", ondelete="CASCADE"), nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("problem_instance.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Evaluation(Base):
    __tablename__ = "evaluation"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    answer_status: Mapped[str] = mapped_column(String(32), nullable=False)
    format_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reasoning_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_checked")
    verifier_version: Mapped[str] = mapped_column(String(32), nullable=False, default="rational-v1")
    input_version: Mapped[int] = mapped_column(nullable=False, default=0)


class TutorTurn(Base):
    __tablename__ = "tutor_turn"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    assistance_level: Mapped[int] = mapped_column(nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="tutor-v1")
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ProgressEvent(Base):
    __tablename__ = "progress_event"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("learner.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    assistance_level: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint("attempts BETWEEN 0 AND 6", name="ck_job_attempts"),
        CheckConstraint("call_count BETWEEN 0 AND 6", name="ck_job_calls"),
        CheckConstraint(
            "state IN ('queued', 'running', 'completed', 'failed', 'canceled', 'waiting')",
            name="ck_job_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="checking")
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    call_count: Mapped[int] = mapped_column(nullable=False, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    retryable: Mapped[bool] = mapped_column(nullable=False, default=True)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class TutorProfileVersion(Base):
    __tablename__ = "tutor_profile_version"
    __table_args__ = (
        UniqueConstraint("profile_id", "version", name="uq_profile_version"),
        CheckConstraint("version >= 1", name="ck_profile_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("administrator.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ProviderProbe(Base):
    __tablename__ = "provider_probe"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    tested_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class RouteSelection(Base):
    __tablename__ = "route_selection"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    routes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ProviderConnection(Base):
    """Admin-managed routing metadata and encrypted, never-public credentials."""

    __tablename__ = "provider_connection"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    credential_revision: Mapped[str] = mapped_column(String(36), nullable=False)


class ProviderPolicy(Base):
    __tablename__ = "provider_policy"
    __table_args__ = (
        CheckConstraint("name = 'active'", name="ck_provider_policy_name"),
        CheckConstraint(
            "app_audience IN ('adult_only', 'mixed')", name="ck_provider_policy_audience"
        ),
    )
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    allow_cloud_inference: Mapped[bool] = mapped_column(nullable=False)
    app_audience: Mapped[str] = mapped_column(String(16), nullable=False)


class ModelCall(Base):
    __tablename__ = "model_call"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Interpretation(Base):
    __tablename__ = "interpretation"
    __table_args__ = (
        UniqueConstraint("submission_id", "version", name="uq_interpretation_version"),
        CheckConstraint("version >= 1", name="ck_interpretation_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    transcription: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(String(128))
    ambiguities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reading: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class DeletionTombstone(Base):
    __tablename__ = "deletion_tombstone"
    learner_id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class PhotoDeletion(Base):
    """Retry private file deletion after its learner/history has been removed."""

    __tablename__ = "photo_deletion"
    __table_args__ = (
        CheckConstraint(
            "length(image_key) = 64 AND image_key NOT GLOB '*[^a-f0-9]*'",
            name="ck_photo_deletion_key",
        ),
    )
    image_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
