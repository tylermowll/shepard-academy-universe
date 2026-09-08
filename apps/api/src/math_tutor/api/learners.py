"""Administrator-managed learner accounts and their signed-in browsers."""

import os
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from math_tutor import auth
from math_tutor.account_names import account_key, display_name
from math_tutor.adapters.db.models import Administrator, DeviceSession, Learner
from math_tutor.api.access import Adult, Database, owned_learner

router = APIRouter(prefix="/api/v1", tags=["learners"])


class LearnerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=64)
    eligibility: Literal["adult", "minor", "unknown"] = "unknown"
    password: str = Field(min_length=1, max_length=auth.MAX_ADMIN_PASSWORD_LENGTH, repr=False)


class LearnerPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alias: str
    eligibility: Literal["adult", "minor", "unknown"]
    enabled: bool
    has_password: bool


class LearnerAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=64)
    password: str | None = Field(
        default=None, min_length=1, max_length=auth.MAX_ADMIN_PASSWORD_LENGTH, repr=False
    )


class LearnerDevicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    expires_at: datetime


class Acknowledged(BaseModel):
    ok: bool = True


def available_name(db: Session, value: str, learner_id: UUID | None = None) -> str:
    try:
        name = display_name(value)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    key = account_key(name)
    query = select(Learner.id).where(Learner.alias_key == key, Learner.deleted_at.is_(None))
    if learner_id is not None:
        query = query.where(Learner.id != learner_id)
    if db.scalar(query) is not None or any(
        account_key(admin) == key for admin in db.scalars(select(Administrator.login_name))
    ):
        raise HTTPException(409, "That username is already in use. Choose a different username.")
    return name


def checked_password(name: str, password: str) -> str:
    try:
        auth.validate_admin_credentials(name, password)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return auth.hash_password(password)


@router.get("/admin/learners", response_model=list[LearnerPublic])
def learners(db: Database, actor: Adult) -> list[Learner]:
    return list(
        db.scalars(select(Learner).where(Learner.deleted_at.is_(None)).order_by(Learner.created_at))
    )


@router.post("/admin/learners", response_model=LearnerPublic, status_code=201)
def create_learner(body: LearnerInput, db: Database, actor: Adult) -> Learner:
    name = available_name(db, body.alias)
    if os.getenv("APP_MODE", "private") == "demo" and name not in {"Orbit", "Delta", "Synthetic"}:
        raise HTTPException(403, "Demo accepts synthetic usernames only.")
    row = Learner(
        alias=name,
        eligibility=body.eligibility,
        password_hash=checked_password(name, body.password),
        local_only_password=len(body.password) < auth.MIN_ADMIN_PASSWORD_LENGTH,
    )
    db.add(row)
    db.flush()
    return row


@router.patch("/admin/learners/{learner_id}/account", response_model=LearnerPublic)
def update_account(
    learner_id: UUID, body: LearnerAccountUpdate, db: Database, actor: Adult
) -> Learner:
    row = owned_learner(db, actor, learner_id)
    name = available_name(db, body.alias, learner_id)
    if body.password is not None:
        row.password_hash = checked_password(name, body.password)
        row.local_only_password = len(body.password) < auth.MIN_ADMIN_PASSWORD_LENGTH
        db.execute(
            update(DeviceSession)
            .where(DeviceSession.learner_id == learner_id)
            .values(revoked_at=auth.utcnow())
        )
    row.alias = name
    db.flush()
    return row


@router.get("/admin/learners/{learner_id}/devices", response_model=list[LearnerDevicePublic])
def learner_devices(learner_id: UUID, db: Database, actor: Adult) -> list[DeviceSession]:
    owned_learner(db, actor, learner_id)
    return list(
        db.scalars(
            select(DeviceSession)
            .where(
                DeviceSession.learner_id == learner_id,
                DeviceSession.revoked_at.is_(None),
                DeviceSession.expires_at > auth.utcnow(),
            )
            .order_by(DeviceSession.created_at.desc())
            .limit(100)
        )
    )


@router.delete("/admin/learners/{learner_id}/devices/{device_id}", response_model=Acknowledged)
def revoke_device(learner_id: UUID, device_id: UUID, db: Database, actor: Adult) -> Acknowledged:
    owned_learner(db, actor, learner_id)
    row = db.get(DeviceSession, device_id)
    if row is None or row.learner_id != learner_id:
        raise HTTPException(404, "Signed-in browser not found.")
    auth.revoke_session(db, row)
    return Acknowledged()


@router.post("/admin/learners/{learner_id}/revoke", response_model=Acknowledged)
def revoke_devices(learner_id: UUID, db: Database, actor: Adult) -> Acknowledged:
    owned_learner(db, actor, learner_id)
    db.execute(
        update(DeviceSession)
        .where(DeviceSession.learner_id == learner_id)
        .values(revoked_at=auth.utcnow())
    )
    return Acknowledged()
