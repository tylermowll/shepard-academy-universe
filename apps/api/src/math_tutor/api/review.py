"""Bounded progress, authenticated exports, immediate revocation and purge."""

from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from math_tutor.adapters.db.models import (
    AuditEvent,
    DeletionTombstone,
    PracticeSession,
    ProgressEvent,
)
from math_tutor.api.access import Adult, Database, Principal, owned_learner
from math_tutor.api.learners import Acknowledged, LearnerPublic
from math_tutor.api.practice import SessionPublic, session_public
from math_tutor.retention import purge_learner, record_deletion

router = APIRouter(prefix="/api/v1", tags=["review"])


class ProgressPublic(BaseModel):
    checked_answers: int
    correct_without_help: int
    correct_with_help: int
    incorrect: int
    note: str = "Counts describe recorded answers, not mastery or measured learning gains."


@router.get("/learners/{learner_id}/progress", response_model=ProgressPublic)
def progress(learner_id: UUID, db: Database, actor: Principal) -> ProgressPublic:
    owned_learner(db, actor, learner_id)
    rows = list(
        db.scalars(
            select(ProgressEvent)
            .where(ProgressEvent.learner_id == learner_id)
            .order_by(ProgressEvent.created_at.desc())
            .limit(10000)
        )
    )
    return ProgressPublic(
        checked_answers=len(rows),
        correct_without_help=sum(r.outcome == "correct" and r.assistance_level == 0 for r in rows),
        correct_with_help=sum(r.outcome == "correct" and r.assistance_level > 0 for r in rows),
        incorrect=sum(r.outcome == "incorrect" for r in rows),
    )


class LearnerExport(BaseModel):
    learner: LearnerPublic
    sessions: list[SessionPublic]


@router.post("/admin/learners/{learner_id}/export", response_model=LearnerExport)
def export(learner_id: UUID, response: Response, db: Database, actor: Adult) -> LearnerExport:
    learner = owned_learner(db, actor, learner_id)
    db.add(
        AuditEvent(actor_id=actor.administrator_id, action="learner_export", subject_id=learner_id)
    )
    response.headers["Content-Disposition"] = 'attachment; filename="learner-export.json"'
    response.headers["Cache-Control"] = "no-store"
    return LearnerExport(
        learner=LearnerPublic.model_validate(learner),
        sessions=[
            session_public(db, row)
            for row in db.scalars(
                select(PracticeSession)
                .where(PracticeSession.learner_id == learner_id)
                .order_by(PracticeSession.created_at)
            )
        ],
    )


@router.delete("/admin/learners/{learner_id}", response_model=Acknowledged)
def delete_learner(learner_id: UUID, db: Database, actor: Adult) -> Acknowledged:
    if db.get(DeletionTombstone, learner_id) is not None:
        return Acknowledged()
    learner = owned_learner(db, actor, learner_id)
    record_deletion(db, learner)
    db.add(
        AuditEvent(actor_id=actor.administrator_id, action="learner_delete", subject_id=learner_id)
    )
    db.commit()
    db.connection(execution_options={"sqlite_begin_immediate": True})
    purge_learner(db, learner_id)
    return Acknowledged()


class Features(BaseModel):
    photos_available: bool
    photo_status: str
    external_problems: bool


@router.get("/learners/{learner_id}/features", response_model=Features)
def features(learner_id: UUID, db: Database, actor: Principal) -> Features:
    import os

    from math_tutor.adapters.providers.contracts import ProviderError
    from math_tutor.providers import authorize_route, effective_configuration

    owned_learner(db, actor, learner_id)
    available, status = True, "Confirm every transcription before checking."
    try:
        _, route = authorize_route(db, effective_configuration(db), "vision", learner_id)
        if route.adapter == "mock":
            status = "Mock photo flow: type the transcription yourself. No handwriting recognition is active."
    except ProviderError as error:
        available, status = False, error.safe_message
    return Features(
        photos_available=available and os.getenv("APP_MODE", "private") != "demo",
        photo_status=status,
        external_problems=os.getenv("ENABLE_EXTERNAL_PROBLEMS", "false") == "true",
    )
