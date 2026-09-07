"""Shared transaction, role, ownership and CSRF boundary."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import DeviceSession, Learner
from math_tutor.api.auth import CSRF_HEADER, SESSION_COOKIE, csrf_matches, engine_for
from math_tutor.auth import get_valid_session, register_login_attempt


def transaction(request: Request) -> Iterator[Session]:
    with Session(engine_for(request), expire_on_commit=False) as db:
        # The delegated phone upload validates, commits, awaits bounded image
        # normalization, then explicitly begins an immediate transaction and
        # revalidates under that lock. Taking the write lock here can deadlock
        # concurrent async uploads: one request can resume and synchronously
        # wait for a lock held by another request whose endpoint needs the same
        # event loop in order to release it.
        deferred_phone_upload = (
            request.method == "POST" and request.url.path == "/api/v1/phone-upload/photos"
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not deferred_phone_upload:
            db.connection(execution_options={"sqlite_begin_immediate": True})
        yield db
        db.commit()


# Commit before sending success: the browser may immediately request the new state.
Database = Annotated[Session, Depends(transaction, scope="function")]


def principal(request: Request, db: Database) -> DeviceSession:
    row = get_valid_session(db, request.cookies.get(SESSION_COOKIE, ""))
    if row is None:
        raise HTTPException(401, "Sign in or pair this device.")
    if row.learner_id is not None:
        learner = db.get(Learner, row.learner_id)
        if learner is None or not learner.enabled or learner.deleted_at is not None:
            raise HTTPException(401, "Device access was revoked.")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not csrf_matches(
        request.headers.get(CSRF_HEADER), row.csrf_token
    ):
        raise HTTPException(403, "CSRF validation failed.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        wait = register_login_attempt("mutation:" + str(row.id), limit=60)
        if wait is not None:
            raise HTTPException(
                429, "Too many operations. Try again shortly.", headers={"Retry-After": "60"}
            )
    return row


Principal = Annotated[DeviceSession, Depends(principal)]


def adult(actor: Principal) -> DeviceSession:
    if actor.role != "adult":
        raise HTTPException(403, "Adult access required.")
    return actor


Adult = Annotated[DeviceSession, Depends(adult)]


def owned_learner(db: Session, actor: DeviceSession, learner_id: UUID) -> Learner:
    if actor.role != "adult" and actor.learner_id != learner_id:
        raise HTTPException(404, "Not found.")
    row = db.get(Learner, learner_id)
    if row is None or not row.enabled or row.deleted_at is not None:
        raise HTTPException(404, "Not found.")
    return row
