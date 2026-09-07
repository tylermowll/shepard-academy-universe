"""Authorize before upload; confirm exactly one interpretation revision before grading."""

import asyncio
import hashlib
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from math_tutor.adapters.db.models import Interpretation, Job, Submission
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import MAX_BYTES, delete_image, normalize, read_image, store_image
from math_tutor.api.access import Database, Principal, principal
from math_tutor.api.practice import (
    OperationPublic,
    assert_available,
    digest,
    operation_public,
    owned_operation,
    owned_problem,
    owned_session,
    request_key,
)

router = APIRouter(prefix="/api/v1", tags=["photos"])
_decode_slots = asyncio.Semaphore(2)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    transcription: str = Field(min_length=1, max_length=4000)
    final_answer: str | None = Field(default=None, max_length=128)


@router.post("/problems/{problem_id}/photos", response_model=OperationPublic, status_code=202)
async def upload_photo(
    problem_id: UUID,
    request: Request,
    db: Database,
    actor: Principal,
    version: int,
    kind: Literal["answer", "question"] = "answer",
) -> OperationPublic:
    if os.getenv("APP_MODE", "private") == "demo":
        raise HTTPException(
            403,
            "Demo accepts supplied synthetic fixtures only. Use private mode for your own photographs.",
        )
    problem = owned_problem(db, actor, problem_id)
    session = owned_session(db, actor, problem.session_id)
    learner_id, key = session.learner_id, request_key(request)
    from math_tutor.providers import authorize_route, effective_configuration

    authorize_route(db, effective_configuration(db), "vision", learner_id)
    if problem.template_id == "external-photo" and not problem.parameters.get("confirmed"):
        kind = "question"
    # Release the authentication transaction before receiving/decoding the image.
    db.commit()
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Image exceeds 8 MiB.")
    payload = digest(
        {
            "problem_id": problem_id,
            "version": version,
            "kind": kind,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    )
    async with _decode_slots:
        try:
            image = await asyncio.to_thread(normalize, bytes(data))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    db.connection(execution_options={"sqlite_begin_immediate": True})
    actor = principal(request, db)
    problem = owned_problem(db, actor, problem_id)
    old = db.scalar(
        select(Submission).where(Submission.learner_id == learner_id, Submission.request_key == key)
    )
    if old:
        if old.payload_hash != payload:
            raise HTTPException(409, "Request key already used with different input.")
        return operation_public(db, old)
    assert_available(db, problem, version)
    from math_tutor.providers import authorize_route, effective_configuration

    config = effective_configuration(db)
    authorize_route(db, config, "vision", learner_id)
    image_key = store_image(image)
    try:
        row = Submission(
            learner_id=learner_id,
            problem_id=problem_id,
            request_key=key,
            payload_hash=payload,
            kind=kind,
            text="",
            image_key=image_key,
            assignment_version=version,
        )
        db.add(row)
        db.flush()
        db.add(Job(submission_id=row.id, stage="interpreting", policy_digest=config.fingerprint()))
        db.commit()
    except Exception:
        delete_image(image_key)
        raise
    return operation_public(db, row)


@router.get("/submissions/{submission_id}/image")
def photo(submission_id: UUID, db: Database, actor: Principal) -> Response:
    row = owned_operation(db, actor, submission_id)
    if row.image_key is None:
        raise HTTPException(404, "Photo expired or unavailable.")
    try:
        data = read_image(row.image_key)
    except OSError:
        raise HTTPException(404, "Photo expired or unavailable.") from None
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/submissions/{submission_id}/confirm-interpretation",
    response_model=OperationPublic,
    status_code=202,
)
def confirm(
    submission_id: UUID, body: Confirmation, db: Database, actor: Principal
) -> OperationPublic:
    row = owned_operation(db, actor, submission_id)
    latest = db.scalar(
        select(Interpretation)
        .where(Interpretation.submission_id == submission_id)
        .order_by(Interpretation.version.desc())
        .limit(1)
    )
    if latest is None:
        raise HTTPException(409, "Interpretation is not ready.")
    if (
        latest.confirmed_at is not None
        and latest.version == body.version + 1
        and latest.transcription == body.transcription
        and latest.final_answer == body.final_answer
    ):
        return operation_public(db, row)
    if (
        row.status != "awaiting_confirmation"
        or latest.version != body.version
        or latest.confirmed_at is not None
    ):
        raise HTTPException(409, "Interpretation changed. Refresh before confirming.")
    db.add(
        Interpretation(
            submission_id=row.id,
            version=latest.version + 1,
            transcription=body.transcription,
            final_answer=body.final_answer,
            ambiguities=[],
            confirmed_at=utcnow(),
        )
    )
    problem = owned_problem(db, actor, row.problem_id)
    if problem.template_id == "external-photo" and not problem.parameters.get("confirmed"):
        problem.problem_text = body.transcription
        problem.parameters = {"confirmed": True}
    job = db.scalar(select(Job).where(Job.submission_id == row.id))
    assert job is not None
    job.state, job.stage, job.lease_token = (
        "queued",
        "checking" if row.kind == "answer" else "tutoring",
        None,
    )
    row.status = "queued"
    db.flush()
    return operation_public(db, row)


@router.post("/images/preview")
async def preview_image(request: Request, db: Database, actor: Principal) -> Response:
    if os.getenv("APP_MODE", "private") == "demo":
        raise HTTPException(403, "Demo does not accept personal photographs.")
    db.commit()
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Image exceeds 8 MiB.")
    async with _decode_slots:
        try:
            normalized = await asyncio.to_thread(normalize, bytes(data))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    return Response(normalized, media_type="image/png", headers={"Cache-Control": "no-store"})
