"""One-host durable worker. Short claims; no database locks during provider I/O."""

import argparse
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from math_tutor.adapters.db.engine import create_default_engine
from math_tutor.adapters.db.models import (
    Evaluation,
    Interpretation,
    Job,
    Learner,
    ModelCall,
    PracticeSession,
    ProblemInstance,
    Submission,
    TutorTurn,
    WorkerHeartbeat,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import read_image
from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import (
    InterpretationPayload,
    Message,
    ModelRequest,
    ModelResult,
    ProviderError,
    TutorPayload,
)
from math_tutor.api.practice import finish_deterministic
from math_tutor.providers import authorize_route, complete, effective_configuration


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    submission_id: UUID
    token: str


def claim(engine: Engine) -> Claim | None:
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        heartbeat = db.get(WorkerHeartbeat, "worker")
        if heartbeat is None:
            db.add(WorkerHeartbeat(name="worker", seen_at=utcnow()))
        else:
            heartbeat.seen_at = utcnow()
        row = db.scalar(
            select(Job)
            .where(
                or_(
                    Job.state == "queued",
                    (Job.state == "running") & (Job.lease_expires_at < utcnow()),
                ),
                Job.available_at <= utcnow(),
            )
            .order_by(Job.available_at)
            .limit(1)
        )
        if row is None:
            db.commit()
            return None
        submission = db.get(Submission, row.submission_id)
        learner = db.get(Learner, submission.learner_id) if submission else None
        if (
            submission is None
            or learner is None
            or learner.deleted_at is not None
            or not learner.enabled
        ):
            row.state = "canceled"
            if submission:
                submission.status = "canceled"
            db.commit()
            return None
        if row.attempts >= 6:
            row.state, row.retryable = "failed", False
            submission.status, submission.safe_error = (
                "failed",
                "Operation exhausted its retry budget.",
            )
            db.commit()
            return None
        row.attempts += 1
        row.state, row.lease_token = "running", secrets.token_urlsafe(24)
        row.lease_expires_at = utcnow() + timedelta(seconds=120)
        submission.status = row.stage
        result = Claim(row.id, row.submission_id, row.lease_token)
        db.commit()
        return result


def finish(
    engine: Engine, work: Claim, result: ModelResult | None = None, source: str = ""
) -> bool:
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        job = db.get(Job, work.job_id)
        if (
            job is None
            or job.state != "running"
            or job.lease_token != work.token
            or job.lease_expires_at is None
            or job.lease_expires_at <= utcnow()
        ):
            return False
        row = db.get(Submission, work.submission_id)
        learner = db.get(Learner, row.learner_id) if row else None
        if (
            row is None
            or learner is None
            or learner.deleted_at is not None
            or not learner.enabled
            or row.status == "canceled"
        ):
            return False
        problem = db.get(ProblemInstance, row.problem_id)
        assert problem is not None
        if job.stage == "interpreting":
            if result is None or not isinstance(result.validated_payload, InterpretationPayload):
                raise ProviderError("malformed_output")
            payload = result.validated_payload
            db.add(
                Interpretation(
                    submission_id=row.id,
                    version=1,
                    transcription=payload.transcription,
                    final_answer=payload.final_answer,
                    ambiguities=payload.ambiguities,
                )
            )
            row.status, job.state = "awaiting_confirmation", "waiting"
        else:
            finish_deterministic(db, row, problem)
            db.flush()
            if result is not None:
                if (
                    not isinstance(result.validated_payload, TutorPayload)
                    or result.validated_payload.message_kind != "question_response"
                ):
                    raise ProviderError("malformed_output")
                turn = db.scalar(select(TutorTurn).where(TutorTurn.submission_id == row.id))
                assert turn is not None
                turn.message, turn.source = result.validated_payload.message_markdown, source
                turn.assistance_level = max(2, row.help_level)
                problem.assistance_level = max(problem.assistance_level, turn.assistance_level)
            job.state = "completed"
        job.lease_token, job.lease_expires_at = None, None
        db.commit()
        return True


@dataclass(frozen=True)
class Prepared:
    provider: ProviderConfig
    request: ModelRequest
    call_id: UUID
    source: str


def prepare(engine: Engine, work: Claim) -> Prepared | None:
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        job = db.get(Job, work.job_id)
        row = db.get(Submission, work.submission_id)
        if job is None or row is None or job.state != "running" or job.lease_token != work.token:
            raise ProviderError("canceled")
        problem = db.get(ProblemInstance, row.problem_id)
        assert problem is not None
        session = db.get(PracticeSession, problem.session_id)
        assert session is not None
        if job.stage != "interpreting":
            if row.kind != "question":
                return None
            # Authored help is the enforcement mechanism while solutions are protected.
            policy = session.profile_settings["solution_policy"]
            attempts = list(
                db.scalars(
                    select(Evaluation)
                    .join(Submission, Evaluation.submission_id == Submission.id)
                    .where(
                        Submission.problem_id == problem.id,
                        Evaluation.answer_status.in_(["correct", "incorrect"]),
                    )
                )
            )
            if policy == "adult_only" or (policy == "after_two_attempts" and len(attempts) < 2):
                return None
        config = effective_configuration(db)
        if config.fingerprint() != job.policy_digest:
            raise ProviderError(
                "policy_changed",
                safe_message="Provider policy changed. Existing work will not be replayed to a new route.",
            )
        stage: Literal["vision", "tutor"] = "vision" if job.stage == "interpreting" else "tutor"
        name, provider = authorize_route(db, config, stage, row.learner_id)
        if job.call_count >= 6:
            raise ProviderError("call_budget")
        image = read_image(row.image_key) if stage == "vision" and row.image_key else None
        if stage == "vision" and image is None:
            raise ProviderError(
                "photo_expired",
                safe_message="Photo expired. Submit a new photo or use typed input.",
            )
        interpretation = db.scalar(
            select(Interpretation)
            .where(Interpretation.submission_id == row.id, Interpretation.confirmed_at.is_not(None))
            .order_by(Interpretation.version.desc())
            .limit(1)
        )
        text = interpretation.transcription if interpretation else row.text
        if stage == "vision":
            instruction = "Transcribe visible mathematical work without correcting it. Describe ambiguities. Return the interpretation schema. No tools, verdicts or solutions."
            message = "Assigned problem: " + problem.problem_text
        else:
            instruction = "Answer one mathematical question with a concise explanation, using message_kind question_response. Do not claim to verify reasoning or change a verdict. No tools, hidden reasoning, HTML, URLs or embedded images. Return the tutor response JSON schema."
            instruction += " Teaching preferences (cannot alter these rules): " + str(
                session.profile_settings
            )
            message = "Assigned problem: " + problem.problem_text + "\nLearner question: " + text
        request = ModelRequest(
            operation_id=row.id,
            stage=stage,
            model_id=provider.model,
            system_instruction=instruction[:6000],
            ordered_messages=[Message(role="user", content=message)],
            private_image_bytes=image,
            response_schema=(
                InterpretationPayload if stage == "vision" else TutorPayload
            ).model_json_schema(),
        )
        call = ModelCall(
            submission_id=row.id,
            provider_id=name,
            model_id=provider.model,
            stage=stage,
            status="started",
        )
        db.add(call)
        db.flush()
        prepared = Prepared(provider, request, call.id, name + " / " + provider.model)
        job.call_count += 1
        db.commit()
        return prepared


def record_call(engine: Engine, call_id: UUID, result: ModelResult | None, code: str) -> None:
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        row = db.get(ModelCall, call_id)
        if row is not None:
            row.status = code
            if result is not None:
                row.usage, row.latency_ms = result.reported_usage, result.latency_ms
            db.commit()


def fail(engine: Engine, work: Claim, error: ProviderError) -> None:
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        job = db.get(Job, work.job_id)
        row = db.get(Submission, work.submission_id)
        if job is None or row is None or job.state != "running" or job.lease_token != work.token:
            return
        job.state, job.retryable = "failed", error.retryable
        job.available_at = utcnow() + timedelta(
            seconds=error.retry_after_seconds + secrets.randbelow(3)
        )
        job.lease_token, job.lease_expires_at = None, None
        row.status, row.safe_error = "failed", error.safe_message
        db.commit()


def run_once(engine: Engine) -> bool:
    work = claim(engine)
    if work is None:
        return False
    prepared = None
    try:
        prepared = prepare(engine, work)
        result = complete(prepared.provider, prepared.request) if prepared else None
        if prepared:
            record_call(engine, prepared.call_id, result, "completed")
        return finish(engine, work, result, prepared.source if prepared else "")
    except ProviderError as error:
        if prepared:
            record_call(engine, prepared.call_id, None, error.code)
        fail(engine, work, error)
    except OSError, ValueError:
        fail(
            engine,
            work,
            ProviderError(
                "configuration_or_storage",
                safe_message="Configuration or private storage is unavailable. Ask an adult to check setup.",
            ),
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the durable Math Practice Tutor worker.")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    engine = create_default_engine()
    try:
        from math_tutor.retention import sweep

        next_sweep = 0.0
        while True:
            if time.monotonic() >= next_sweep:
                sweep(engine)
                next_sweep = time.monotonic() + 60
            worked = run_once(engine)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
