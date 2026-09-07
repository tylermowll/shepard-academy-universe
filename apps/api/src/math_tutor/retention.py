"""Revocation before idempotent purge; content-free tombstones survive backup restore."""

import logging
import os
import re
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from math_tutor import settings
from math_tutor.adapters.db.models import (
    DeletionTombstone,
    DeviceSession,
    Job,
    Learner,
    PairingRequest,
    PhoneUpload,
    PhotoDeletion,
    PracticeSession,
    ProblemInstance,
    Submission,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import delete_image, object_root

logger = logging.getLogger(__name__)


def limits() -> tuple[int, int]:
    photo_hours = int(os.getenv("PHOTO_RETENTION_HOURS", "24"))
    history_days = int(os.getenv("HISTORY_RETENTION_DAYS", "30"))
    if not 1 <= photo_hours <= 24 or not 1 <= history_days <= 365:
        raise ValueError("Photo retention must be 1–24 hours and history 1–365 days.")
    return photo_hours, history_days


def photo_expired(row: Submission) -> bool:
    """Logical expiry must hold even while physical deletion is delayed."""
    photo_hours, _ = limits()
    return row.created_at <= utcnow() - timedelta(hours=photo_hours)


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
            queue_photo_deletion(db, image_key)
    db.execute(delete(Learner).where(Learner.id == learner_id))


def queue_photo_deletion(db: Session, image_key: str) -> None:
    """Commit a cleanup reference atomically with removal of its owning content."""
    db.execute(
        insert(PhotoDeletion)
        .values(image_key=image_key, created_at=utcnow())
        .on_conflict_do_nothing(index_elements=["image_key"])
    )


def purge_queued_photos(engine: Engine) -> None:
    with Session(engine) as db:
        keys = list(db.scalars(select(PhotoDeletion.image_key)))
    removed = []
    for key in keys:
        try:
            # No database write lock during filesystem I/O. Keys are never reused.
            delete_image(key)
        except OSError:
            logger.warning("Photo cleanup deferred; check private storage availability.")
        else:
            removed.append(key)
    if removed:
        with Session(engine) as db:
            db.connection(execution_options={"sqlite_begin_immediate": True})
            db.execute(delete(PhotoDeletion).where(PhotoDeletion.image_key.in_(removed)))
            db.commit()


def _purge_photo(row: Submission) -> None:
    if row.image_key:
        try:
            delete_image(row.image_key)
        except OSError:
            # Keep the durable reference so the next sweep can retry storage failure.
            logger.warning("Photo cleanup deferred; check private storage availability.")
            return
        row.image_key = None


def purge_completed_photo(engine: Engine, submission_id: UUID) -> None:
    """Run only after completion commits; a crash leaves work for the next sweep."""
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        row = db.get(Submission, submission_id)
        if row is not None and row.status == "completed":
            _purge_photo(row)
        db.commit()


def sweep(engine: Engine) -> None:
    photo_hours, history_days = limits()
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        for learner in db.scalars(select(Learner).where(Learner.deleted_at.is_not(None))):
            purge_learner(db, learner.id)
        for row in db.scalars(
            select(Submission).where(
                Submission.image_key.is_not(None),
                or_(
                    Submission.status == "completed",
                    Submission.created_at < utcnow() - timedelta(hours=photo_hours),
                ),
            )
        ):
            _purge_photo(row)
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
                queue_photo_deletion(db, key)
        db.execute(delete(PracticeSession).where(PracticeSession.id.in_(expired)))
        referenced = set(
            db.scalars(select(Submission.image_key).where(Submission.image_key.is_not(None)))
        )
        db.execute(delete(PairingRequest).where(PairingRequest.expires_at < utcnow()))
        db.execute(delete(PhoneUpload).where(PhoneUpload.expires_at < utcnow()))
        db.execute(delete(DeviceSession).where(DeviceSession.expires_at < utcnow()))
        db.commit()
    purge_queued_photos(engine)
    # A one-hour grace period protects freshly written objects not yet committed.
    cutoff = (utcnow() - timedelta(hours=1)).timestamp()
    for path in object_root().iterdir():
        if re.fullmatch(r"[a-f0-9]{64}", path.name) is None or path.is_symlink():
            continue
        try:
            if path.is_file() and path.name not in referenced and path.stat().st_mtime < cutoff:
                delete_image(path.name)
        except OSError:
            logger.warning("Orphan photo cleanup deferred; check private storage availability.")
