"""Storage outages cannot expose expired photos or strand deletion and tutoring."""

import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx2 import AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_workflows import adult as adult
from test_workflows import anyio_backend as anyio_backend
from test_workflows import engine as engine
from test_workflows import learner_ids, photo_bytes, send, start

from math_tutor import retention, worker
from math_tutor.adapters.db.engine import create_engine_for_url
from math_tutor.adapters.db.models import (
    Learner,
    PhotoDeletion,
    PracticeSession,
    Submission,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import delete_image, object_path, store_image


async def upload(adult: AsyncClient, problem_id: str) -> UUID:
    response = await adult.post(
        f"/api/v1/problems/{problem_id}/photos?version=1",
        content=photo_bytes(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


def image_key(engine: Engine, operation: UUID) -> str:
    with Session(engine) as db:
        row = db.get(Submission, operation)
        assert row is not None and row.image_key is not None
        return row.image_key


@pytest.mark.anyio
@pytest.mark.parametrize("cause", ["learner", "history"])
async def test_deleted_content_is_purged_and_photos_retry_after_storage_recovery(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    learner, other = await learner_ids(adult)
    session_id, problem = await start(adult, learner)
    operation = await upload(adult, problem["id"])
    key = image_key(engine, operation)
    path = object_path(key)
    assert path.exists()

    def unavailable(target: str) -> None:
        if target == key:
            raise PermissionError("Synthetic private path and content must not reach logs")
        delete_image(target)

    with monkeypatch.context() as patch:
        patch.setattr(retention, "delete_image", unavailable)
        if cause == "learner":
            response = await adult.delete(f"/api/v1/admin/learners/{learner}")
            assert response.status_code == 200, response.text
            assert (await adult.delete(f"/api/v1/admin/learners/{learner}")).status_code == 200
        else:
            with Session(engine) as db:
                session = db.get(PracticeSession, UUID(session_id))
                assert session is not None
                session.updated_at = utcnow() - timedelta(days=31)
                db.commit()
        retention.sweep(engine)
        with Session(engine) as db:
            assert db.get(PracticeSession, UUID(session_id)) is None
            assert db.get(Submission, operation) is None
            assert db.get(PhotoDeletion, key) is not None
            if cause == "learner":
                assert db.get(Learner, UUID(learner)) is None
        assert (await adult.get(f"/api/v1/submissions/{operation}/image")).status_code == 404
        assert (await adult.get(f"/api/v1/sessions/{session_id}")).status_code == 404
        assert session_id not in (await adult.get("/api/v1/sessions")).text

        # Another learner's work still completes while one object cannot be removed.
        _, other_problem = await start(adult, other)
        other_operation = await send(adult, other_problem)
        assert worker.run_once(engine)
        assert (await adult.get(f"/api/v1/operations/{other_operation['id']}")).json()[
            "status"
        ] == "completed"
        assert path.exists()

    # A new process/connection can discover the retry without the original content.
    reopened = create_engine_for_url(str(engine.url))
    try:
        retention.sweep(reopened)
        retention.sweep(reopened)
        with Session(reopened) as db:
            assert db.get(PhotoDeletion, key) is None
        assert not path.exists()
    finally:
        reopened.dispose()


@pytest.mark.anyio
async def test_cleanup_queue_rolls_back_with_content_deletion(
    adult: AsyncClient, engine: Engine
) -> None:
    learner = (await learner_ids(adult))[0]
    _, problem = await start(adult, learner)
    operation = await upload(adult, problem["id"])
    key = image_key(engine, operation)
    with Session(engine) as db:
        retention.purge_learner(db, UUID(learner))
        assert db.get(PhotoDeletion, key) is not None
        db.rollback()
    with Session(engine) as db:
        assert db.get(Learner, UUID(learner)) is not None
        assert db.get(Submission, operation) is not None
        assert db.get(PhotoDeletion, key) is None
    assert object_path(key).exists()


def test_cleanup_survives_crash_after_unlink_without_holding_database_lock(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = store_image(photo_bytes())
    with Session(engine) as db:
        retention.queue_photo_deletion(db, key)
        retention.queue_photo_deletion(db, key)
        db.commit()

    def crash(target: str) -> None:
        with closing(sqlite3.connect(str(engine.url.database), timeout=0)) as contender:
            contender.execute("BEGIN IMMEDIATE")
            contender.rollback()
        delete_image(target)
        raise SystemExit("Synthetic crash after unlink")

    with monkeypatch.context() as patch:
        patch.setattr(retention, "delete_image", crash)
        with pytest.raises(SystemExit, match="Synthetic crash"):
            retention.purge_queued_photos(engine)
    assert not object_path(key).exists()
    with Session(engine) as db:
        assert list(db.scalars(select(PhotoDeletion.image_key))) == [key]
    retention.purge_queued_photos(engine)
    with Session(engine) as db:
        assert list(db.scalars(select(PhotoDeletion.image_key))) == []


@pytest.mark.anyio
@pytest.mark.parametrize("hours", [1, 24])
async def test_expired_photo_is_hidden_and_never_sent_to_provider_during_cleanup_failure(
    adult: AsyncClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    hours: int,
) -> None:
    monkeypatch.setenv("PHOTO_RETENTION_HOURS", str(hours))
    _, problem = await start(adult, (await learner_ids(adult))[0])
    operation = await upload(adult, problem["id"])
    key = image_key(engine, operation)
    assert (await adult.get(f"/api/v1/submissions/{operation}/image")).status_code == 200
    with Session(engine) as db:
        row = db.get(Submission, operation)
        assert row is not None
        row.created_at = utcnow() - timedelta(hours=hours, seconds=1)
        db.commit()

    def unavailable(_key: str) -> None:
        raise OSError("Synthetic storage outage")

    def forbidden(*_args: object) -> None:
        pytest.fail("Expired photo must not be read or sent to a provider")

    monkeypatch.setattr(retention, "delete_image", unavailable)
    monkeypatch.setattr(worker, "read_image", forbidden)
    monkeypatch.setattr(worker, "complete", forbidden)
    retention.sweep(engine)
    assert object_path(key).exists()
    assert (await adult.get(f"/api/v1/submissions/{operation}/image")).status_code == 404
    assert worker.run_once(engine)
    result = (await adult.get(f"/api/v1/operations/{operation}")).json()
    assert result["status"] == "failed"
    assert result["safe_error"].startswith("Photo expired.")


def test_orphan_failure_does_not_block_other_cleanup_or_log_private_details(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    blocked, removable = store_image(photo_bytes()), store_image(photo_bytes())
    for key in (blocked, removable):
        timestamp = (utcnow() - timedelta(hours=2)).timestamp()
        os.utime(object_path(key), (timestamp, timestamp))

    def unavailable(key: str) -> None:
        if key == blocked:
            raise OSError("Synthetic private-content-marker " + str(object_path(key)))
        delete_image(key)

    with monkeypatch.context() as patch:
        patch.setattr(retention, "delete_image", unavailable)
        retention.sweep(engine)
    assert object_path(blocked).exists()
    assert not object_path(removable).exists()
    assert "Orphan photo cleanup deferred" in caplog.text
    assert "private-content-marker" not in caplog.text
    assert blocked not in caplog.text
    retention.sweep(engine)
    assert not object_path(blocked).exists()


@pytest.mark.parametrize("phase", ["retention", "job"])
@pytest.mark.parametrize("failure", [OSError, OperationalError])
def test_worker_loop_recovers_from_storage_and_database_outages(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    phase: str,
    failure: type[OSError] | type[OperationalError],
) -> None:
    original_sweep, original_run = retention.sweep, worker.run_once
    attempts, jobs, now = 0, 0, 0.0
    sleeps: list[float] = []

    def fail_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure is OperationalError:
                raise OperationalError("private SQL", {"text": "private input"}, Exception())
            raise OSError("private path")

    def sweep(current: Engine) -> None:
        if phase == "retention":
            fail_once()
        original_sweep(current)

    def run_once(current: Engine) -> bool:
        nonlocal jobs
        if phase == "job":
            fail_once()
        jobs += 1
        if attempts >= 2:
            raise KeyboardInterrupt
        return original_run(current)

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += 61  # Advance the scheduler without waiting in the test.

    monkeypatch.setattr(sys, "argv", ["worker"])
    monkeypatch.setattr(worker, "create_default_engine", lambda: engine)
    monkeypatch.setattr(retention, "sweep", sweep)
    monkeypatch.setattr(worker, "run_once", run_once)
    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(time, "monotonic", lambda: now)
    worker.main()
    assert attempts == 2
    assert jobs >= 1
    assert sleeps == ([5] if phase == "job" else [1])
    assert "private path" not in caplog.text
    assert "private SQL" not in caplog.text
    assert "private input" not in caplog.text


@pytest.mark.parametrize("phase", ["retention", "job"])
def test_worker_once_reports_failure_without_raw_storage_details(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    def unavailable(_engine: Engine) -> bool:
        raise OSError("private path")

    monkeypatch.setattr(sys, "argv", ["worker", "--once"])
    monkeypatch.setattr(worker, "create_default_engine", lambda: engine)
    monkeypatch.setattr(
        retention if phase == "retention" else worker,
        "sweep" if phase == "retention" else "run_once",
        unavailable,
    )
    with pytest.raises(SystemExit, match="failed; check private storage/database") as result:
        worker.main()
    assert "private path" not in str(result.value)
