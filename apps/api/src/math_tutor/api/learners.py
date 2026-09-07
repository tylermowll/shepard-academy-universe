"""Managed aliases and browser-bound, single-use device pairing."""

import os
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from math_tutor import auth
from math_tutor.adapters.db.models import DeviceSession, Learner, PairingRequest
from math_tutor.api.access import Adult, Database, owned_learner
from math_tutor.api.auth import (
    client_key,
    login_csrf_valid,
    require_secret,
    secure_cookies,
    set_session_cookie,
)

router = APIRouter(prefix="/api/v1", tags=["learners"])
PAIR_COOKIE = "mt_pair"


class LearnerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    alias: str = Field(min_length=1, max_length=64)
    eligibility: Literal["adult", "minor", "unknown"] = "unknown"


class LearnerPublic(LearnerInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enabled: bool


class PairPublic(BaseModel):
    id: UUID
    expires_at: datetime
    approved: bool


class Approval(BaseModel):
    learner_id: UUID


class Acknowledged(BaseModel):
    ok: bool = True


@router.get("/admin/learners", response_model=list[LearnerPublic])
def learners(db: Database, actor: Adult) -> list[Learner]:
    return list(
        db.scalars(select(Learner).where(Learner.deleted_at.is_(None)).order_by(Learner.created_at))
    )


@router.post("/admin/learners", response_model=LearnerPublic, status_code=201)
def create_learner(body: LearnerInput, db: Database, actor: Adult) -> Learner:
    if os.getenv("APP_MODE", "private") == "demo" and body.alias not in {
        "Orbit",
        "Delta",
        "Synthetic",
    }:
        raise HTTPException(403, "Demo accepts synthetic aliases only.")
    row = Learner(alias=body.alias, eligibility=body.eligibility)
    db.add(row)
    db.flush()
    return row


@router.post("/admin/learners/{learner_id}/revoke", response_model=Acknowledged)
def revoke_devices(learner_id: UUID, db: Database, actor: Adult) -> Acknowledged:
    owned_learner(db, actor, learner_id)
    db.execute(
        update(DeviceSession)
        .where(DeviceSession.learner_id == learner_id)
        .values(revoked_at=auth.utcnow())
    )
    for row in db.scalars(select(PairingRequest).where(PairingRequest.learner_id == learner_id)):
        db.delete(row)
    return Acknowledged()


def pairing_limit(request: Request) -> None:
    wait = auth.register_login_attempt("pair:" + client_key(request))
    if wait is not None:
        raise HTTPException(
            429, "Too many pairing requests. Try again later.", headers={"Retry-After": "60"}
        )


@router.post("/pairing/requests", response_model=PairPublic, status_code=201)
def request_pairing(request: Request, response: Response, db: Database) -> PairPublic:
    if not login_csrf_valid(request, require_secret()):
        raise HTTPException(403, "CSRF validation failed.")
    pairing_limit(request)
    token = auth.new_opaque_token()
    row = PairingRequest(
        token_hash=auth.hash_opaque_token(token), expires_at=auth.utcnow() + timedelta(minutes=5)
    )
    db.add(row)
    db.flush()
    response.set_cookie(
        PAIR_COOKIE,
        token,
        max_age=300,
        httponly=True,
        secure=secure_cookies(),
        samesite="strict",
        path="/api/v1/pairing",
    )
    return PairPublic(id=row.id, expires_at=row.expires_at, approved=False)


def bound_pair(request: Request, db: Database, pair_id: UUID) -> PairingRequest:
    row = db.get(PairingRequest, pair_id)
    token = request.cookies.get(PAIR_COOKIE, "")
    if (
        row is None
        or row.token_hash != auth.hash_opaque_token(token)
        or row.expires_at <= auth.utcnow()
        or row.consumed_at is not None
    ):
        raise HTTPException(404, "Pairing request unavailable or expired.")
    return row


@router.get("/pairing/requests/{pair_id}", response_model=PairPublic)
def pairing_status(pair_id: UUID, request: Request, db: Database) -> PairPublic:
    row = bound_pair(request, db, pair_id)
    return PairPublic(id=row.id, expires_at=row.expires_at, approved=row.learner_id is not None)


@router.post("/admin/pairing/{pair_id}/approve", response_model=Acknowledged)
def approve_pair(pair_id: UUID, body: Approval, db: Database, actor: Adult) -> Acknowledged:
    owned_learner(db, actor, body.learner_id)
    row = db.get(PairingRequest, pair_id)
    if row is None or row.expires_at <= auth.utcnow() or row.consumed_at is not None:
        raise HTTPException(404, "Pairing request unavailable or expired.")
    if row.learner_id is not None and row.learner_id != body.learner_id:
        raise HTTPException(409, "Request already approved.")
    row.learner_id = body.learner_id
    return Acknowledged()


@router.post("/pairing/requests/{pair_id}/claim", response_model=Acknowledged)
def claim_pair(pair_id: UUID, request: Request, response: Response, db: Database) -> Acknowledged:
    if not login_csrf_valid(request, require_secret()):
        raise HTTPException(403, "CSRF validation failed.")
    row = bound_pair(request, db, pair_id)
    learner = db.get(Learner, row.learner_id) if row.learner_id else None
    if learner is None or not learner.enabled or learner.deleted_at is not None:
        raise HTTPException(409, "Waiting for adult approval.")
    old = auth.get_valid_session(db, request.cookies.get("mt_session", ""))
    if old is not None:
        auth.revoke_session(db, old)
    token = auth.new_opaque_token()
    db.add(
        DeviceSession(
            token_hash=auth.hash_opaque_token(token),
            role="learner",
            learner_id=learner.id,
            csrf_token=auth.new_csrf_token(),
            expires_at=auth.utcnow() + auth.SESSION_LIFETIME,
        )
    )
    row.consumed_at = auth.utcnow()
    set_session_cookie(response, token, int(auth.SESSION_LIFETIME.total_seconds()))
    response.delete_cookie(PAIR_COOKIE, path="/api/v1/pairing")
    return Acknowledged()
