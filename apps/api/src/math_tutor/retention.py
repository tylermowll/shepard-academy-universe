"""Revocation before idempotent purge; content-free tombstones survive backup restore."""

import os
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from math_tutor import settings
from math_tutor.adapters.db.models import (
    DeletionTombstone,
    DeviceSession,
    Job,
    Learner,
    PairingRequest,
    PracticeSession,
    ProblemInstance,
    Submission,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import delete_image, object_root


def limits() -> tuple[int, int]:
    photo_hours = int(os.getenv("PHOTO_RETENTION_HOURS", "24"))
    history_days = int(os.getenv("HISTORY_RETENTION_DAYS", "30"))
    if not 1 <= photo_hours <= 24 or not 1 <= history_days <= 365:
        raise ValueError("Photo retention must be 1–24 hours and history 1–365 days.")
    return photo_hours, history_days


def record_deletion(db: Session, learner: Learner) -> None:
    path = settings.database_path().parent / "deletions.jsonl"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a") as output:
        output.write(str(learner.id) + "\n")
        output.flush()
        os.fsync(output.fileno())
    if db.get(DeletionTombstone, learner.id) is None:
        db.add(DeletionTombstone(learner_id=learner.id))
    learner.enabled, learner.deleted_at = False, utcnow()
    db.execute(
        update(DeviceSession)
        .where(DeviceSession.learner_id == learner.id)
        .values(revoked_at=utcnow())
    )
    ids = select(Submission.id).where(Submission.learner_id == learner.id)
    db.execute(
        update(Job).where(Job.submission_id.in_(ids)).values(state="canceled", lease_token=None)
    )
    db.execute(
        update(Submission)
        .where(Submission.learner_id == learner.id, Submission.status != "completed")
        .values(status="canceled")
    )


def purge_learner(db: Session, learner_id: UUID) -> None:
    for image_key in db.scalars(
        select(Submission.image_key).where(
            Submission.learner_id == learner_id, Submission.image_key.is_not(None)
        )
    ):
        if image_key:
            delete_image(image_key)
    db.execute(delete(Learner).where(Learner.id == learner_id))


def sweep(engine: Engine) -> None:
    photo_hours, history_days = limits()
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        for learner in db.scalars(select(Learner).where(Learner.deleted_at.is_not(None))):
            purge_learner(db, learner.id)
        for row in db.scalars(
            select(Submission).where(
                Submission.image_key.is_not(None),
                Submission.created_at < utcnow() - timedelta(hours=photo_hours),
            )
        ):
            if row.image_key:
                delete_image(row.image_key)
                row.image_key = None
        expired = list(
            db.scalars(
                select(PracticeSession.id).where(
                    PracticeSession.updated_at < utcnow() - timedelta(days=history_days)
                )
            )
        )
        for key in db.scalars(
            select(Submission.image_key)
            .join(ProblemInstance, Submission.problem_id == ProblemInstance.id)
            .join(PracticeSession, ProblemInstance.session_id == PracticeSession.id)
            .where(PracticeSession.id.in_(expired), Submission.image_key.is_not(None))
        ):
            if key:
                delete_image(key)
        db.execute(delete(PracticeSession).where(PracticeSession.id.in_(expired)))
        referenced = set(
            db.scalars(select(Submission.image_key).where(Submission.image_key.is_not(None)))
        )
        db.execute(delete(PairingRequest).where(PairingRequest.expires_at < utcnow()))
        db.execute(delete(DeviceSession).where(DeviceSession.expires_at < utcnow()))
        db.commit()
    # A one-hour grace period protects freshly written objects not yet committed.
    cutoff = (utcnow() - timedelta(hours=1)).timestamp()
    for path in object_root().iterdir():
        if path.is_file() and path.name not in referenced and path.stat().st_mtime < cutoff:
            delete_image(path.name)
