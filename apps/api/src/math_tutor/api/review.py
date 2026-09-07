"""Bounded progress, authenticated exports, immediate revocation and purge."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from math_tutor.adapters.db.models import (
    AuditEvent,
    DeletionTombstone,
    PracticeSession,
    ProblemInstance,
    ProgressEvent,
)
from math_tutor.api.access import Adult, Database, Principal, owned_learner
from math_tutor.api.learners import Acknowledged, LearnerPublic
from math_tutor.api.practice import SessionPublic, session_public
from math_tutor.api.tutoring import TutoringSessionPublic, public_session
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


class ReferenceMaterialPublic(BaseModel):
    problem_id: UUID
    source: Literal["reference_text", "reference_photo"]
    text: str


class LearnerExport(BaseModel):
    learner: LearnerPublic
    sessions: list[SessionPublic | TutoringSessionPublic]
    reference_material: list[ReferenceMaterialPublic]


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
            public_session(db, row) if row.mode == "ai_tutor" else session_public(db, row)
            for row in db.scalars(
                select(PracticeSession)
                .where(PracticeSession.learner_id == learner_id)
                .order_by(PracticeSession.created_at)
            )
        ],
        reference_material=[
            ReferenceMaterialPublic(
                problem_id=problem.id,
                source=problem.parameters["reference_source"],
                text=problem.parameters["reference"],
            )
            for problem in db.scalars(
                select(ProblemInstance)
                .join(PracticeSession, PracticeSession.id == ProblemInstance.session_id)
                .where(PracticeSession.learner_id == learner_id, PracticeSession.mode == "ai_tutor")
                .order_by(PracticeSession.created_at, ProblemInstance.position)
            )
            if problem.parameters.get("reference_source") in {"reference_text", "reference_photo"}
            and problem.parameters.get("reference")
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
    tutoring_available: bool
    tutor_status: str
    text_processing: str


@router.get("/learners/{learner_id}/features", response_model=Features)
def features(learner_id: UUID, db: Database, actor: Principal) -> Features:
    import os

    from math_tutor.adapters.providers.contracts import ProviderError
    from math_tutor.providers import authorize_route, effective_configuration

    owned_learner(db, actor, learner_id)
    available, status = (
        True,
        "Clear photo readings continue automatically; unclear work gets specific retake advice.",
    )
    try:
        _, route = authorize_route(db, effective_configuration(db), "vision", learner_id)
        if route.adapter == "mock":
            status = "The mock recognizes one public synthetic fixture only. Configure a vision model to read your handwriting."
        else:
            boundary = (
                "a cloud provider"
                if route.data_boundary == "cloud"
                else "your computer or private network"
            )
            status += " Photos are processed by " + boundary + "."
    except ProviderError as error:
        available, status = False, error.safe_message
    tutoring_available, tutor_status, text_processing = (
        True,
        "AI tutoring is available through the selected provider.",
        "unavailable",
    )
    try:
        _, tutor = authorize_route(db, effective_configuration(db), "tutor", learner_id)
        text_processing = "mock" if tutor.adapter == "mock" else tutor.data_boundary
        if tutor.adapter == "mock":
            tutor_status = "Synthetic mock responses only. Configure a real text and vision provider for tutoring and handwriting recognition."
    except ProviderError as error:
        tutoring_available, tutor_status = False, error.safe_message
    if os.getenv("APP_MODE", "private") == "demo":
        tutor_status = "AI tutoring and personal photos require a private deployment. The public demo cannot accept your work."
    return Features(
        photos_available=available and os.getenv("APP_MODE", "private") != "demo",
        photo_status=status,
        external_problems=os.getenv("ENABLE_EXTERNAL_PROBLEMS", "false") == "true",
        tutoring_available=tutoring_available and os.getenv("APP_MODE", "private") != "demo",
        tutor_status=tutor_status,
        text_processing=text_processing,
    )
