"""Owned practice operations with canonical request identity and immutable results."""

import hashlib
import json
import os
import secrets
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import (
    DEFAULT_PROFILE,
    DeviceSession,
    Evaluation,
    Interpretation,
    Job,
    PracticeSession,
    ProblemInstance,
    ProgressEvent,
    Submission,
    TutorProfileVersion,
    TutorTurn,
)
from math_tutor.api.access import Database, Principal, owned_learner
from math_tutor.api.learners import Acknowledged
from math_tutor.api.profiles import ProfileSettings
from math_tutor.api.schemas import ProblemInstancePublic
from math_tutor.domain.math import SKILLS, Verdict, generate, help_text, verify

router = APIRouter(prefix="/api/v1", tags=["practice"])
ACTIVE = {"queued", "checking", "tutoring", "interpreting", "awaiting_confirmation"}


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: UUID
    profile_version_id: UUID | None = None


class ProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str = "fractions.add"


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


class SubmissionInput(VersionInput):
    kind: Literal["answer", "question", "hint"] = "answer"
    text: str = Field(default="", max_length=4000)
    help_level: int = Field(default=0, ge=0, le=4)
    work_text: str = Field(default="", max_length=4000)


class VerdictPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    answer_status: str
    format_status: str
    reasoning_status: str
    verifier_version: str


class OperationPublic(BaseModel):
    id: UUID
    problem_id: UUID
    kind: str
    text: str
    status: str
    work_text: str
    safe_error: str | None
    created_at: datetime
    verdict: VerdictPublic | None = None
    message: str | None = None
    source: str | None = None
    assistance_level: int = 0
    interpretation: str | None = None
    interpretation_version: int | None = None
    interpreted_final_answer: str | None = None
    ambiguities: list[str] = Field(default_factory=list)


class ProblemPublic(ProblemInstancePublic):
    version: int
    assistance_level: int
    operations: list[OperationPublic]


class SessionPublic(BaseModel):
    id: UUID
    learner_id: UUID
    status: str
    profile: ProfileSettings
    problems: list[ProblemPublic]


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    learner_id: UUID
    status: str
    created_at: datetime


def request_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key", "")
    if not 1 <= len(key) <= 128 or not key.isascii():
        raise HTTPException(400, "A bounded Idempotency-Key is required.")
    return key


def digest(body: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def owned_session(db: Session, actor: DeviceSession, session_id: UUID) -> PracticeSession:
    row = db.get(PracticeSession, session_id)
    if row is None:
        raise HTTPException(404, "Not found.")
    owned_learner(db, actor, row.learner_id)
    return row


def owned_problem(db: Session, actor: DeviceSession, problem_id: UUID) -> ProblemInstance:
    row = db.get(ProblemInstance, problem_id)
    if row is None:
        raise HTTPException(404, "Not found.")
    owned_session(db, actor, row.session_id)
    return row


def owned_operation(db: Session, actor: DeviceSession, operation_id: UUID) -> Submission:
    row = db.get(Submission, operation_id)
    if row is None:
        raise HTTPException(404, "Not found.")
    owned_learner(db, actor, row.learner_id)
    return row


def operation_public(db: Session, row: Submission) -> OperationPublic:
    evaluation = db.scalar(select(Evaluation).where(Evaluation.submission_id == row.id))
    turn = db.scalar(select(TutorTurn).where(TutorTurn.submission_id == row.id))
    interpretation = db.scalar(
        select(Interpretation)
        .where(Interpretation.submission_id == row.id)
        .order_by(Interpretation.version.desc())
        .limit(1)
    )
    return OperationPublic(
        id=row.id,
        problem_id=row.problem_id,
        kind=row.kind,
        text=row.text,
        work_text=row.work_text,
        status=row.status,
        safe_error=row.safe_error,
        created_at=row.created_at,
        verdict=VerdictPublic.model_validate(evaluation) if evaluation else None,
        message=turn.message if turn else None,
        source=turn.source if turn else None,
        assistance_level=turn.assistance_level if turn else 0,
        interpretation=interpretation.transcription if interpretation else None,
        interpretation_version=interpretation.version if interpretation else None,
        interpreted_final_answer=interpretation.final_answer if interpretation else None,
        ambiguities=interpretation.ambiguities if interpretation else [],
    )


def problem_public(db: Session, row: ProblemInstance) -> ProblemPublic:
    data = ProblemInstancePublic.model_validate(row).model_dump()
    return ProblemPublic(
        **data,
        version=row.version,
        assistance_level=row.assistance_level,
        operations=[
            operation_public(db, op)
            for op in db.scalars(
                select(Submission)
                .where(Submission.problem_id == row.id)
                .order_by(Submission.created_at)
            )
        ],
    )


def session_public(db: Session, row: PracticeSession) -> SessionPublic:
    return SessionPublic(
        id=row.id,
        learner_id=row.learner_id,
        status=row.status,
        profile=ProfileSettings.model_validate(row.profile_settings),
        problems=[
            problem_public(db, p)
            for p in db.scalars(
                select(ProblemInstance)
                .where(ProblemInstance.session_id == row.id)
                .order_by(ProblemInstance.position)
            )
        ],
    )


@router.get("/catalog", response_model=list[str])
def catalog(actor: Principal) -> list[str]:
    return list(SKILLS)


@router.get("/sessions", response_model=list[SessionSummary])
def sessions(db: Database, actor: Principal) -> list[PracticeSession]:
    query = select(PracticeSession).order_by(PracticeSession.created_at.desc()).limit(100)
    if actor.role != "adult":
        query = query.where(PracticeSession.learner_id == actor.learner_id)
    return list(db.scalars(query))


@router.post("/sessions", response_model=SessionPublic, status_code=201)
def start_session(
    body: SessionInput, request: Request, db: Database, actor: Principal
) -> SessionPublic:
    owned_learner(db, actor, body.learner_id)
    key, payload = request_key(request), digest(body.model_dump())
    old = db.scalar(
        select(PracticeSession).where(
            PracticeSession.learner_id == body.learner_id, PracticeSession.request_key == key
        )
    )
    if old:
        if old.payload_hash != payload:
            raise HTTPException(409, "Request key already used with different input.")
        return session_public(db, old)
    profile = (
        db.get(TutorProfileVersion, body.profile_version_id) if body.profile_version_id else None
    )
    if body.profile_version_id and profile is None:
        raise HTTPException(404, "Profile version unavailable.")
    row = PracticeSession(
        learner_id=body.learner_id,
        request_key=key,
        payload_hash=payload,
        profile_version_id=body.profile_version_id,
        profile_settings=dict(profile.settings if profile else DEFAULT_PROFILE),
    )
    db.add(row)
    db.flush()
    return session_public(db, row)


@router.get("/sessions/{session_id}", response_model=SessionPublic)
def read_session(session_id: UUID, db: Database, actor: Principal) -> SessionPublic:
    return session_public(db, owned_session(db, actor, session_id))


@router.post("/sessions/{session_id}/problems", response_model=ProblemPublic, status_code=201)
def next_problem(
    session_id: UUID, body: ProblemInput, request: Request, db: Database, actor: Principal
) -> ProblemPublic:
    session = owned_session(db, actor, session_id)
    key = request_key(request)
    problems = list(
        db.scalars(select(ProblemInstance).where(ProblemInstance.session_id == session_id))
    )
    for old in problems:
        if old.request_key == key:
            if old.skill_id != body.skill_id:
                raise HTTPException(409, "Request key already used with different input.")
            return problem_public(db, old)
    if (
        session.status != "open"
        or len(problems) >= session.profile_settings["session_problem_limit"]
    ):
        raise HTTPException(409, "Session is finished. Start another session.")
    if any(p.status == "assigned" for p in problems):
        raise HTTPException(409, "Finish or skip the current problem first.")
    if body.skill_id not in session.profile_settings["topics"]:
        raise HTTPException(422, "This skill is not enabled in this session's profile.")
    try:
        problem = generate(
            body.skill_id, secrets.randbelow(2**31), session.profile_settings["difficulty"]
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    row = ProblemInstance(
        session_id=session_id,
        template_id=body.skill_id,
        template_version=1,
        skill_id=body.skill_id,
        seed=problem.seed,
        position=len(problems),
        parameters=problem.parameters,
        problem_text=problem.text,
        expected_result={"value": problem.expected},
        format_constraints={"simplest_form": problem.simplest},
        request_key=key,
    )
    db.add(row)
    db.flush()
    return problem_public(db, row)


def assert_available(db: Session, problem: ProblemInstance, version: int) -> None:
    if problem.version != version or problem.status != "assigned":
        raise HTTPException(409, "Problem changed. Refresh before continuing.")
    active = db.scalar(
        select(Submission.id).where(
            Submission.problem_id == problem.id, Submission.status.in_(ACTIVE)
        )
    )
    if active is not None:
        raise HTTPException(409, "An operation is already active for this problem.")


def finish_deterministic(db: Session, row: Submission, problem: ProblemInstance) -> None:
    if row.status == "completed":
        return
    session = db.get(PracticeSession, problem.session_id)
    assert session is not None
    expected = str(problem.expected_result.get("value", "unverifiable"))
    interpretation = db.scalar(
        select(Interpretation)
        .where(Interpretation.submission_id == row.id, Interpretation.confirmed_at.is_not(None))
        .order_by(Interpretation.version.desc())
        .limit(1)
    )
    if row.image_key and interpretation is None:
        raise ValueError("Photo requires confirmation before verification.")
    if row.kind == "answer":
        verdict = verify(
            (interpretation.final_answer or interpretation.transcription)
            if interpretation
            else row.text,
            expected if expected != "unverifiable" else "0",
            bool((problem.format_constraints or {}).get("simplest_form", True)),
            equation=problem.skill_id == "equations.linear",
        )
        if problem.template_id == "external-photo":
            verdict = Verdict("unverifiable", "unverifiable")
        db.add(
            Evaluation(
                submission_id=row.id,
                answer_status=verdict.answer_status,
                format_status=verdict.format_status,
                input_version=interpretation.version if interpretation else 0,
            )
        )
        message = {
            "correct": "Your final answer has the correct value.",
            "incorrect": "That final answer has a different value. Try revising, or request a hint.",
            "unverifiable": "I cannot check that input. Use a bounded integer, fraction, or decimal.",
            "no_answer": "Enter a final answer to check.",
        }[verdict.answer_status]
        if problem.template_id == "external-photo":
            message = "This external problem has no trusted answer key. Its answer remains unverifiable; an adult can review your confirmed work."
        if verdict.format_status == "needs_simplification":
            message += " Reduce the fraction to simplest form."
        if verdict.answer_status in {"correct", "incorrect"}:
            db.add(
                ProgressEvent(
                    submission_id=row.id,
                    learner_id=row.learner_id,
                    skill_id=problem.skill_id,
                    outcome=verdict.answer_status,
                    assistance_level=problem.assistance_level,
                )
            )
        if verdict.answer_status == "correct" and verdict.format_status == "satisfied":
            problem.status = "completed"
        level = problem.assistance_level
    else:
        level = max(1, row.help_level)
        message = (
            help_text(problem.skill_id, level, problem.problem_text, expected)
            if problem.template_id != "external-photo"
            else "This external problem is outside the authored catalog. I can discuss confirmed wording, but cannot verify its answer. No failed attempt was recorded."
        )
        problem.assistance_level = max(problem.assistance_level, level)
    db.add(
        TutorTurn(
            submission_id=row.id,
            message=message,
            source="built-in explanation",
            assistance_level=level,
        )
    )
    row.status = "completed"
    from math_tutor.adapters.db.types import utcnow

    session.updated_at = utcnow()
    problem.version += 1


@router.post("/problems/{problem_id}/submissions", response_model=OperationPublic, status_code=202)
def submit(
    problem_id: UUID, body: SubmissionInput, request: Request, db: Database, actor: Principal
) -> OperationPublic:
    problem = owned_problem(db, actor, problem_id)
    session = owned_session(db, actor, problem.session_id)
    key, payload = request_key(request), digest({"problem_id": problem_id, **body.model_dump()})
    old = db.scalar(
        select(Submission).where(
            Submission.learner_id == session.learner_id, Submission.request_key == key
        )
    )
    if old:
        if old.payload_hash != payload:
            raise HTTPException(409, "Request key already used with different input.")
        return operation_public(db, old)
    assert_available(db, problem, body.version)
    if problem.template_id == "external-photo" and not problem.parameters.get("confirmed"):
        raise HTTPException(409, "Confirm the external question photograph before submitting work.")
    if os.getenv("APP_MODE", "private") == "demo" and body.work_text:
        raise HTTPException(403, "Demo does not accept free-text work.")
    if os.getenv("APP_MODE", "private") == "demo" and body.text and body.kind != "hint":
        import re

        if body.kind != "answer" or re.fullmatch(r"[x=+\-0-9/ .]{1,128}", body.text) is None:
            raise HTTPException(
                403, "Demo accepts synthetic numeric answers and authored hints only."
            )
    if body.kind != "answer" and body.help_level == 4:
        policy = session.profile_settings["solution_policy"]
        attempts = len(
            list(
                db.scalars(
                    select(Evaluation)
                    .join(Submission, Evaluation.submission_id == Submission.id)
                    .where(
                        Submission.problem_id == problem_id,
                        Evaluation.answer_status.in_(["correct", "incorrect"]),
                    )
                )
            )
        )
        if actor.role != "adult" and (
            policy == "adult_only" or (policy == "after_two_attempts" and attempts < 2)
        ):
            raise HTTPException(403, "Full solution is not available yet.")
    row = Submission(
        learner_id=session.learner_id,
        problem_id=problem_id,
        request_key=key,
        payload_hash=payload,
        kind=body.kind,
        text=body.text,
        help_level=body.help_level,
        assignment_version=body.version,
        work_text=body.work_text,
    )
    db.add(row)
    db.flush()
    from math_tutor.providers import effective_configuration

    db.add(
        Job(
            submission_id=row.id,
            stage="checking" if row.kind == "answer" else "tutoring",
            policy_digest=effective_configuration(db).fingerprint(),
        )
    )
    db.flush()
    return operation_public(db, row)


@router.post("/problems/{problem_id}/skip", response_model=Acknowledged)
def skip(problem_id: UUID, body: VersionInput, db: Database, actor: Principal) -> Acknowledged:
    problem = owned_problem(db, actor, problem_id)
    assert_available(db, problem, body.version)
    problem.status = "skipped"
    problem.version += 1
    return Acknowledged()


@router.post("/sessions/{session_id}/finish", response_model=Acknowledged)
def finish_session(session_id: UUID, db: Database, actor: Principal) -> Acknowledged:
    row = owned_session(db, actor, session_id)
    active = db.scalar(
        select(Submission.id)
        .join(ProblemInstance, Submission.problem_id == ProblemInstance.id)
        .where(ProblemInstance.session_id == session_id, Submission.status.in_(ACTIVE))
    )
    if active:
        raise HTTPException(409, "Wait for or cancel the active operation first.")
    row.status = "completed"
    for problem in db.scalars(
        select(ProblemInstance).where(
            ProblemInstance.session_id == session_id, ProblemInstance.status == "assigned"
        )
    ):
        problem.status = "skipped"
        problem.version += 1
    return Acknowledged()


@router.get("/operations/{operation_id}", response_model=OperationPublic)
def read_operation(operation_id: UUID, db: Database, actor: Principal) -> OperationPublic:
    return operation_public(db, owned_operation(db, actor, operation_id))


@router.post("/operations/{operation_id}/cancel", response_model=OperationPublic)
def cancel_operation(operation_id: UUID, db: Database, actor: Principal) -> OperationPublic:
    row = owned_operation(db, actor, operation_id)
    if row.status == "completed":
        raise HTTPException(409, "Operation already completed.")
    row.status = "canceled"
    job = db.scalar(select(Job).where(Job.submission_id == row.id))
    if job:
        job.state, job.lease_token = "canceled", None
    return operation_public(db, row)


@router.post("/operations/{operation_id}/retry", response_model=OperationPublic, status_code=202)
def retry_operation(operation_id: UUID, db: Database, actor: Principal) -> OperationPublic:
    row = owned_operation(db, actor, operation_id)
    job = db.scalar(select(Job).where(Job.submission_id == row.id))
    if row.status != "failed" or job is None or not job.retryable or job.attempts >= 6:
        raise HTTPException(409, "Operation cannot be retried.")
    problem = owned_problem(db, actor, row.problem_id)
    assert_available(db, problem, row.assignment_version)
    row.status, row.safe_error = "queued", None
    job.state, job.lease_token = "queued", None
    return operation_public(db, row)


@router.post(
    "/sessions/{session_id}/external-problem", response_model=ProblemPublic, status_code=201
)
def external_problem(
    session_id: UUID, request: Request, db: Database, actor: Principal
) -> ProblemPublic:
    if os.getenv("ENABLE_EXTERNAL_PROBLEMS", "false") != "true":
        raise HTTPException(404, "External problem mode is disabled.")
    session = owned_session(db, actor, session_id)
    key = request_key(request)
    problems = list(
        db.scalars(select(ProblemInstance).where(ProblemInstance.session_id == session_id))
    )
    for old in problems:
        if old.request_key == key:
            if old.template_id != "external-photo":
                raise HTTPException(409, "Request key already used.")
            return problem_public(db, old)
    if (
        session.status != "open"
        or any(p.status == "assigned" for p in problems)
        or len(problems) >= session.profile_settings["session_problem_limit"]
    ):
        raise HTTPException(409, "Finish the current problem or start another session.")
    row = ProblemInstance(
        session_id=session_id,
        template_id="external-photo",
        template_version=1,
        skill_id="external.unverified",
        seed=0,
        position=len(problems),
        parameters={"confirmed": False},
        problem_text="Photograph the external question, then confirm its transcription.",
        expected_result={},
        format_constraints=None,
        request_key=key,
    )
    db.add(row)
    db.flush()
    return problem_public(db, row)
