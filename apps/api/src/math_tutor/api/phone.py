"""One-photo delegation: a phone never receives the owner's browser session."""

import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from math_tutor import settings
from math_tutor.adapters.db.models import DeviceSession, PhoneUpload, ProblemInstance, Submission
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import delete_image
from math_tutor.api.access import Database, Principal
from math_tutor.api.auth import client_key
from math_tutor.api.photos import enqueue_photo, receive_image
from math_tutor.api.practice import (
    VersionInput,
    assert_available,
    owned_problem,
    owned_session,
    request_key,
)
from math_tutor.auth import hash_opaque_token, register_login_attempt
from math_tutor.providers import authorize_route, effective_configuration

router = APIRouter(prefix="/api/v1", tags=["phone camera"])


class PhoneUploadLink(BaseModel):
    id: UUID
    url: str
    expires_at: datetime


class PhoneUploadInfo(BaseModel):
    expires_at: datetime
    received: bool
    problem_text: str
    processing: str


class PhoneReceipt(BaseModel):
    received: bool = True


def link_secret(identifier: UUID) -> str:
    # Reconstruct the same link after a lost creation acknowledgement, without
    # storing a bearer secret. Domain separation from session/CSRF credentials.
    return hmac.new(
        settings.session_secret().encode(),
        f"phone-photo-v1:{identifier}".encode(),
        hashlib.sha256,
    ).hexdigest()


def private_mode() -> None:
    if os.getenv("APP_MODE", "private") == "demo":
        raise HTTPException(403, "Use private practice for phone photographs.")


def validate_grant(db: Session, grant: PhoneUpload) -> ProblemInstance:
    now = utcnow()
    issuer = db.get(DeviceSession, grant.issuer_id)
    if (
        grant.expires_at <= now
        or grant.revoked_at is not None
        or issuer is None
        or issuer.revoked_at is not None
        or issuer.expires_at <= now
    ):
        raise HTTPException(410, "This photo link ended. Create a new link on your computer.")
    problem = owned_problem(db, issuer, grant.problem_id)
    session = owned_session(db, issuer, problem.session_id)
    if grant.submission_id is None:
        if session.status != "open":
            raise HTTPException(410, "This practice session has finished.")
        assert_available(db, problem, grant.version)
        config = effective_configuration(db)
        if config.fingerprint() != grant.policy_digest:
            raise HTTPException(
                409, "Photo processing settings changed. Create a new link on your computer."
            )
        authorize_route(db, config, "vision", session.learner_id)
    return problem


def presented_grant(request: Request, db: Session, *, rate_limit: bool = True) -> PhoneUpload:
    private_mode()
    token = request.headers.get("X-Photo-Token", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise HTTPException(401, "Open the photo link from your computer.")
    if rate_limit and request.method != "GET":
        wait = register_login_attempt("phone:" + client_key(request), limit=30)
        if wait is not None:
            raise HTTPException(429, "Too many photo requests. Try again in a minute.")
    grant = db.scalar(select(PhoneUpload).where(PhoneUpload.token_hash == hash_opaque_token(token)))
    if grant is None:
        raise HTTPException(410, "This photo link ended. Create a new link on your computer.")
    validate_grant(db, grant)
    return grant


@router.post(
    "/problems/{problem_id}/phone-uploads", response_model=PhoneUploadLink, status_code=201
)
def create_link(
    problem_id: UUID,
    body: VersionInput,
    request: Request,
    db: Database,
    actor: Principal,
) -> PhoneUploadLink:
    private_mode()
    problem = owned_problem(db, actor, problem_id)
    session = owned_session(db, actor, problem.session_id)
    if session.status != "open" or problem.template_id == "external-photo":
        raise HTTPException(409, "Choose an active app-assigned problem for phone capture.")
    key = request_key(request)
    old = db.scalar(
        select(PhoneUpload).where(
            PhoneUpload.issuer_id == actor.id,
            PhoneUpload.request_key == key,
        )
    )
    if old:
        if old.problem_id != problem_id or old.version != body.version:
            raise HTTPException(409, "Request key already used with different input.")
        validate_grant(db, old)
        grant = old
    else:
        assert_available(db, problem, body.version)
        config = effective_configuration(db)
        authorize_route(db, config, "vision", session.learner_id)
        db.execute(
            update(PhoneUpload)
            .where(
                PhoneUpload.problem_id == problem_id,
                PhoneUpload.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )
        identifier = uuid4()
        grant = PhoneUpload(
            id=identifier,
            token_hash=hash_opaque_token(link_secret(identifier)),
            issuer_id=actor.id,
            problem_id=problem_id,
            version=body.version,
            policy_digest=config.fingerprint(),
            request_key=key,
            expires_at=utcnow() + timedelta(minutes=5),
        )
        db.add(grant)
        db.flush()
    return PhoneUploadLink(
        id=grant.id,
        url=f"{settings.app_public_origin()}/#capture={link_secret(grant.id)}",
        expires_at=grant.expires_at,
    )


@router.delete("/phone-uploads/{identifier}", response_model=PhoneReceipt)
def revoke_link(identifier: UUID, db: Database, actor: Principal) -> PhoneReceipt:
    grant = db.get(PhoneUpload, identifier)
    if grant is None:
        return PhoneReceipt(received=False)
    owned_problem(db, actor, grant.problem_id)
    grant.revoked_at = utcnow()
    return PhoneReceipt(received=False)


@router.get("/phone-upload", response_model=PhoneUploadInfo)
def info(request: Request, db: Database) -> PhoneUploadInfo:
    grant = presented_grant(request, db)
    if grant.submission_id is not None:
        # A receipt carries no interpretation, history, or grading result.
        return PhoneUploadInfo(
            expires_at=grant.expires_at, received=True, problem_text="", processing=""
        )
    problem = db.get(ProblemInstance, grant.problem_id)
    assert problem is not None
    config = effective_configuration(db)
    provider = config.providers[config.routes.vision]
    processing = (
        "An external model provider will read this photo."
        if provider.data_boundary == "cloud"
        else "Your computer or a model on its private network will read this photo."
    )
    if provider.adapter == "mock":
        processing = "Synthetic test mode only: no real handwriting reader is configured. Configure a vision model on the computer to read your work."
    return PhoneUploadInfo(
        expires_at=grant.expires_at,
        received=False,
        problem_text=problem.problem_text,
        processing=processing,
    )


@router.post("/phone-upload/preview")
async def preview(request: Request, db: Database) -> Response:
    grant = presented_grant(request, db)
    if grant.submission_id is not None:
        raise HTTPException(409, "This photo has already been sent. Return to your computer.")
    db.commit()
    image, _ = await receive_image(request)
    db.expire_all()
    grant = presented_grant(request, db, rate_limit=False)
    if grant.submission_id is not None:
        raise HTTPException(409, "This photo has already been sent.")
    return Response(image, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/phone-upload/photos", response_model=PhoneReceipt, status_code=202)
async def upload(request: Request, db: Database) -> PhoneReceipt:
    presented_grant(request, db)
    key = request_key(request)
    db.commit()
    image, checksum = await receive_image(request)
    db.connection(execution_options={"sqlite_begin_immediate": True})
    db.expire_all()
    grant = presented_grant(request, db, rate_limit=False)
    if grant.submission_id is not None:
        old = db.get(Submission, grant.submission_id)
        if (
            old is None
            or old.payload_hash != checksum
            or old.request_key != f"phone:{grant.id}:{key}"
        ):
            raise HTTPException(
                409, "This link already received a different photo. Return to your computer."
            )
        # Release the explicit immediate transaction before the async request
        # returns and dependency teardown is scheduled. A concurrent retry must
        # never wait on a successful duplicate receipt.
        db.commit()
        return PhoneReceipt()
    problem = db.get(ProblemInstance, grant.problem_id)
    issuer = db.get(DeviceSession, grant.issuer_id)
    assert problem is not None and issuer is not None
    session = owned_session(db, issuer, problem.session_id)
    # Keep the final idempotency identity within the submission column's bound.
    if len(key) > 80:
        raise HTTPException(400, "Photo request key must be at most 80 characters.")
    row = enqueue_photo(
        db,
        problem,
        session.learner_id,
        grant.version,
        "answer",
        f"phone:{grant.id}:{key}",
        checksum,
        image,
    )
    try:
        grant.submission_id = row.id
        db.commit()
    except Exception:
        if row.image_key:
            delete_image(row.image_key)
        raise
    return PhoneReceipt()
