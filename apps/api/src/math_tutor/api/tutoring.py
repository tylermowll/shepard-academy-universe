"""Multi-subject sessions: learner-owned activities, model-authored guidance."""

from __future__ import annotations

import os
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import (
    DEFAULT_PROFILE,
    Job,
    PracticeSession,
    ProblemInstance,
    Submission,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.api.access import Database, Principal, owned_learner
from math_tutor.api.practice import (
    ACTIVE,
    ProblemPublic,
    digest,
    owned_session,
    problem_public,
    request_key,
)
from math_tutor.providers import authorize_route, effective_configuration

router = APIRouter(prefix="/api/v1/tutor", tags=["AI tutoring"])
Initiative = Literal["tutor_led", "balanced", "learner_led"]
Difficulty = Literal["introductory", "standard", "challenge"]


def session_difficulty(row: PracticeSession) -> Difficulty:
    value = row.profile_settings.get("difficulty", "standard")
    return cast(
        Difficulty, value if value in {"introductory", "standard", "challenge"} else "standard"
    )


class TutorSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initiative: Initiative
    difficulty: Difficulty | None = None


class TutorActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    difficulty: Difficulty | None = None
    source: Literal["topic", "reference_text", "reference_photo"] = "topic"
    reference_text: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def validate_reference(self) -> TutorActivityInput:
        if self.source == "reference_text" and not (self.reference_text or "").strip():
            raise ValueError("Reference text is required.")
        if self.source != "reference_text" and self.reference_text is not None:
            raise ValueError("Only a text reference accepts reference_text.")
        return self


class TutoringSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: UUID
    topic: str = Field(min_length=1, max_length=500)
    initiative: Initiative = "balanced"
    difficulty: Difficulty = "standard"
    initial_activity: TutorActivityInput | None = None


class TutoringSessionPublic(BaseModel):
    id: UUID
    learner_id: UUID
    status: str
    topic: str
    initiative: Initiative
    difficulty: Difficulty
    problems: list[ProblemPublic]


def public_session(db: Session, row: PracticeSession) -> TutoringSessionPublic:
    return TutoringSessionPublic(
        id=row.id,
        learner_id=row.learner_id,
        status=row.status,
        topic=row.topic,
        initiative=cast(Initiative, row.initiative),
        difficulty=session_difficulty(row),
        problems=[
            problem_public(db, item)
            for item in db.scalars(
                select(ProblemInstance)
                .where(ProblemInstance.session_id == row.id)
                .order_by(ProblemInstance.position)
            )
        ],
    )


def private_tutoring() -> None:
    if os.getenv("APP_MODE", "private") == "demo":
        raise HTTPException(
            403,
            "AI tutoring accepts private work only in a private deployment. The public demo is synthetic.",
        )


def owned_tutoring_session(db: Session, actor: Principal, session_id: UUID) -> PracticeSession:
    row = owned_session(db, actor, session_id)
    if row.mode != "ai_tutor":
        raise HTTPException(404, "Tutoring session not found.")
    return row


@router.post("/sessions", response_model=TutoringSessionPublic, status_code=201)
def create_session(
    body: TutoringSessionInput, request: Request, db: Database, actor: Principal
) -> TutoringSessionPublic:
    private_tutoring()
    owned_learner(db, actor, body.learner_id)
    if not body.topic.strip():
        raise HTTPException(422, "Choose a topic or describe what you want to practice.")
    key, payload = request_key(request), digest(body.model_dump())
    old = db.scalar(
        select(PracticeSession).where(
            PracticeSession.learner_id == body.learner_id, PracticeSession.request_key == key
        )
    )
    if old:
        if old.payload_hash != payload or old.mode != "ai_tutor":
            raise HTTPException(409, "Request key already used with different input.")
        return public_session(db, old)
    authorize_route(db, effective_configuration(db), "tutor", body.learner_id)
    row = PracticeSession(
        learner_id=body.learner_id,
        mode="ai_tutor",
        topic=body.topic.strip(),
        initiative=body.initiative,
        profile_settings={**DEFAULT_PROFILE, "difficulty": body.difficulty},
        request_key=key,
        payload_hash=payload,
    )
    db.add(row)
    db.flush()
    if body.initial_activity is not None:
        activity(row.id, body.initial_activity, request, db, actor)
    return public_session(db, row)


@router.get("/sessions", response_model=list[TutoringSessionPublic])
def sessions(db: Database, actor: Principal) -> list[TutoringSessionPublic]:
    query = (
        select(PracticeSession)
        .where(PracticeSession.mode == "ai_tutor")
        .order_by(PracticeSession.created_at.desc())
        .limit(100)
    )
    if actor.role != "adult":
        query = query.where(PracticeSession.learner_id == actor.learner_id)
    return [public_session(db, row) for row in db.scalars(query)]


@router.get("/sessions/{session_id}", response_model=TutoringSessionPublic)
def read_session(session_id: UUID, db: Database, actor: Principal) -> TutoringSessionPublic:
    return public_session(db, owned_tutoring_session(db, actor, session_id))


@router.post("/sessions/{session_id}/settings", response_model=TutoringSessionPublic)
def settings(
    session_id: UUID, body: TutorSettingsInput, db: Database, actor: Principal
) -> TutoringSessionPublic:
    private_tutoring()
    row = owned_tutoring_session(db, actor, session_id)
    if row.status != "open":
        raise HTTPException(409, "This session is finished.")
    row.initiative = body.initiative
    if body.difficulty is not None:
        row.profile_settings = {**row.profile_settings, "difficulty": body.difficulty}
    row.updated_at = utcnow()
    return public_session(db, row)


@router.post("/sessions/{session_id}/activities", response_model=ProblemPublic, status_code=201)
def activity(
    session_id: UUID, body: TutorActivityInput, request: Request, db: Database, actor: Principal
) -> ProblemPublic:
    private_tutoring()
    session = owned_tutoring_session(db, actor, session_id)
    key, payload = request_key(request), digest(body.model_dump())
    problems = list(
        db.scalars(
            select(ProblemInstance)
            .where(ProblemInstance.session_id == session_id)
            .order_by(ProblemInstance.position)
        )
    )
    for old in problems:
        if old.request_key == key:
            if old.parameters.get("request_digest") != payload:
                raise HTTPException(409, "Request key already used with different input.")
            return problem_public(db, old)
    if session.status != "open" or len(problems) >= 100:
        raise HTTPException(409, "Start another session to continue.")
    for old in problems:
        if old.status == "assigned":
            active = db.scalar(
                select(Submission.id).where(
                    Submission.problem_id == old.id, Submission.status.in_(ACTIVE)
                )
            )
            if active:
                raise HTTPException(409, "Wait for or cancel the current operation first.")
            # The learner requests moving on. Model output never owns this transition.
            old.status = (
                "completed" if old.parameters.get("activity_state") == "ready" else "skipped"
            )
            old.version += 1
    config = effective_configuration(db)
    authorize_route(db, config, "tutor", session.learner_id)
    photo = body.source == "reference_photo"
    if photo:
        authorize_route(db, config, "vision", session.learner_id)
    if body.difficulty is not None:
        session.profile_settings = {**session.profile_settings, "difficulty": body.difficulty}
    session.updated_at = utcnow()
    row = ProblemInstance(
        session_id=session.id,
        template_id="ai-activity-v1",
        template_version=1,
        skill_id="open.subject",
        seed=0,
        position=len(problems),
        parameters={
            "activity_state": "reference_capture" if photo else "generating",
            "reference_source": body.source,
            "reference": body.reference_text or "",
            "request_digest": payload,
        },
        problem_text="Photograph the source material. The tutor will create a different practice activity, not solve the original assignment."
        if photo
        else "Preparing a new practice activity…",
        expected_result={},
        format_constraints=None,
        request_key=key,
    )
    db.add(row)
    db.flush()
    if not photo:
        operation = Submission(
            learner_id=session.learner_id,
            problem_id=row.id,
            request_key=f"activity:{row.id}",
            payload_hash=payload,
            kind="hint",
            text="Create a new practice activity.",
            assignment_version=row.version,
        )
        db.add(operation)
        db.flush()
        db.add(
            Job(submission_id=operation.id, stage="tutoring", policy_digest=config.fingerprint())
        )
        db.flush()
    return problem_public(db, row)
