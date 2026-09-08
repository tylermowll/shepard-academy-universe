"""AI tutoring is the primary workflow; synthetic providers, real on-disk SQLite."""

from datetime import timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest
from httpx2 import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_workflows import adult as adult
from test_workflows import anyio_backend as anyio_backend
from test_workflows import client, learner_ids, pair_learner, phone_link, photo_bytes
from test_workflows import engine as engine

from math_tutor import worker
from math_tutor.adapters.db.models import (
    Evaluation,
    Job,
    PracticeSession,
    ProblemInstance,
    ProgressEvent,
    Submission,
    TutorTurn,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import (
    ActivityPayload,
    FeedbackPayload,
    ModelRequest,
    ModelResult,
    ProviderError,
    ReadingPayload,
)


async def tutor_session(adult: AsyncClient, topic: str = "Scientific evidence") -> dict[str, Any]:
    response = await adult.post(
        "/api/v1/tutor/sessions",
        json={
            "learner_id": (await learner_ids(adult))[0],
            "topic": topic,
            "initiative": "balanced",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


async def activity(adult: AsyncClient, session: dict[str, Any], **body: Any) -> dict[str, Any]:
    response = await adult.post(
        f"/api/v1/tutor/sessions/{session['id']}/activities",
        json=body or {"source": "topic"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


async def latest(adult: AsyncClient, session: dict[str, Any]) -> dict[str, Any]:
    response = await adult.get(f"/api/v1/tutor/sessions/{session['id']}")
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json()["problems"][-1])


def install_tutor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    quality: Literal["clear", "uncertain", "unreadable"] = "clear",
    reference: str | None = None,
) -> list[ModelRequest]:
    requests: list[ModelRequest] = []

    def respond(_provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        requests.append(request)
        result: ActivityPayload | ReadingPayload | FeedbackPayload
        if request.purpose == "generate":
            result = ActivityPayload(
                problem_text="Compare two seedlings grown with different amounts of light. Explain what evidence you would collect.",
                concept_focus="Using evidence to support a claim",
            )
        elif request.purpose == "read":
            result = ReadingPayload(
                transcription=reference
                or "1. I measured each seedling.\n2. I think the taller one had more light.",
                quality=quality,
                confidence=0.95 if quality == "clear" else 0.5,
                ambiguities=[] if quality == "clear" else ["The second line overlaps the first."],
                organization_feedback=[
                    "Leave a blank line between numbered observations and your conclusion."
                ],
                rejection_reason=None
                if quality == "clear"
                else "Rewrite the overlapping lines with more space and retake the photo.",
            )
        else:
            result = FeedbackPayload(
                strengths=["You recorded a measurement before making a claim."],
                guidance=[
                    "Explain how your measurement supports the claim, and consider what else you would keep the same."
                ],
                next_step="Add one sentence connecting the observation to your claim.",
                concepts=["Evidence", "Fair comparisons"],
            )
        return ModelResult(model_id=request.model_id, validated_payload=result)

    monkeypatch.setattr(worker, "complete", respond)
    return requests


@pytest.mark.anyio
@pytest.mark.parametrize(
    "topic",
    [
        "Writing a persuasive paragraph",
        "Reading an excerpt",
        "History: interpreting primary sources",
        "Social studies: local government",
        "Science: photosynthesis",
        "Calculus and handwritten proofs",
    ],
)
async def test_any_topic_generates_without_level_or_answer_key(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, topic: str
) -> None:
    requests = install_tutor(monkeypatch)
    session = await tutor_session(adult, topic)
    pending = await activity(adult, session)
    assert pending["activity_state"] == "generating"
    assert pending["operations"][0]["status"] == "queued"
    assert pending["operations"][0]["kind"] == "generation"
    assert worker.run_once(engine)
    ready = await latest(adult, session)
    assert ready["activity_state"] == "ready"
    assert ready["concept_focus"] == "Using evidence to support a claim"
    assert topic in requests[0].ordered_messages[-1].content
    assert requests[0].purpose == "generate"
    assert "expected_result" not in str(ready)
    with Session(engine) as db:
        problem = db.get(ProblemInstance, UUID(ready["id"]))
        assert problem is not None and problem.expected_result == {}
        assert db.scalar(select(func.count()).select_from(Evaluation)) == 0
    assert (
        await adult.post(
            f"/api/v1/sessions/{session['id']}/problems",
            json={"skill_id": "fractions.add"},
            headers={"Idempotency-Key": str(uuid4())},
        )
    ).status_code == 409


@pytest.mark.anyio
async def test_next_activity_saves_difficulty_atomically_and_deduplicates(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = install_tutor(monkeypatch)
    session = await tutor_session(adult)
    path = f"/api/v1/tutor/sessions/{session['id']}/activities"
    body = {"source": "topic", "difficulty": "introductory"}
    headers = {"Idempotency-Key": str(uuid4())}
    first = await adult.post(path, json=body, headers=headers)
    assert first.status_code == 201
    duplicate = await adult.post(path, json=body, headers=headers)
    assert duplicate.status_code == 201 and duplicate.json()["id"] == first.json()["id"]
    blocked = await adult.post(
        path,
        json={"source": "topic", "difficulty": "challenge"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert blocked.status_code == 409
    saved = (await adult.get(f"/api/v1/tutor/sessions/{session['id']}")).json()
    assert saved["difficulty"] == "introductory" and len(saved["problems"]) == 1
    assert worker.run_once(engine)
    assert "Difficulty: easier" in requests[-1].system_instruction
    await activity(adult, session, source="topic", difficulty="challenge")
    assert worker.run_once(engine)
    assert "Difficulty: harder" in requests[-1].system_instruction


@pytest.mark.anyio
async def test_photo_guidance_revision_context_and_next_activity(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = install_tutor(monkeypatch)
    session = await tutor_session(adult)
    await activity(adult, session)
    assert worker.run_once(engine)
    problem = await latest(adult, session)
    link = await phone_link(adult, problem)
    async with client(engine) as phone:
        phone.headers["X-Photo-Token"] = link["url"].split("#capture=")[1]
        assert (
            await phone.post(
                "/api/v1/phone-upload/photos",
                content=photo_bytes(),
                headers={"Idempotency-Key": str(uuid4())},
            )
        ).status_code == 202
        assert (await phone.get(f"/api/v1/tutor/sessions/{session['id']}")).status_code == 401
    assert worker.run_once(engine)
    reading = (await latest(adult, session))["operations"][-1]
    assert reading["status"] == "queued"  # a persisted reading, no approval
    assert reading["interpretation"].startswith("1. I measured")
    assert reading["reading"]["can_continue"] is True
    assert reading["reading"]["organization_feedback"]
    assert reading["feedback"] is None and reading["verdict"] is None
    read_request = requests[-1]
    assert read_request.purpose == "read"
    assert read_request.max_output_tokens == 16384
    assert (
        await adult.post(
            f"/api/v1/submissions/{reading['id']}/confirm-interpretation",
            json={"version": 1, "transcription": "altered"},
        )
    ).status_code == 409
    assert worker.run_once(engine)
    problem = await latest(adult, session)
    review = problem["operations"][-1]
    assert review["status"] == "completed" and review["feedback"]["guidance"]
    assert review["verdict"] is None and problem["status"] == "assigned"
    assert (
        requests[-1].purpose == "review"
        and "1. I measured" in requests[-1].ordered_messages[-1].content
    )
    revision = {
        "version": problem["version"],
        "kind": "answer",
        "text": "The measured growth supports my claim because I compared the change over one week.",
    }
    headers = {"Idempotency-Key": str(uuid4())}
    first = await adult.post(
        f"/api/v1/problems/{problem['id']}/submissions", json=revision, headers=headers
    )
    duplicate = await adult.post(
        f"/api/v1/problems/{problem['id']}/submissions", json=revision, headers=headers
    )
    assert first.status_code == 202 and duplicate.json()["id"] == first.json()["id"]
    assert worker.run_once(engine)
    assert any(
        "Add one sentence" in message.content
        for message in requests[-1].ordered_messages
        if message.role == "assistant"
    )
    assert any(
        "1. I measured" in message.content
        for message in requests[-1].ordered_messages
        if message.role == "user"
    )
    await activity(adult, session)
    assert worker.run_once(engine)
    assert "measured growth supports" in str(requests[-1].ordered_messages)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Evaluation)) == 0
        assert db.scalar(select(func.count()).select_from(ProgressEvent)) == 0
        row = db.get(Submission, UUID(review["id"]))
        assert row is not None and row.image_key is None


@pytest.mark.anyio
@pytest.mark.parametrize("quality", ["uncertain", "unreadable"])
async def test_unclear_reading_rejects_without_tutoring_or_approval(
    adult: AsyncClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    quality: Literal["uncertain", "unreadable"],
) -> None:
    requests = install_tutor(monkeypatch, quality=quality)
    session = await tutor_session(adult)
    await activity(adult, session)
    assert worker.run_once(engine)
    problem = await latest(adult, session)
    uploaded = await adult.post(
        f"/api/v1/problems/{problem['id']}/photos?version={problem['version']}",
        content=photo_bytes(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert uploaded.status_code == 202
    assert worker.run_once(engine)
    result = (await latest(adult, session))["operations"][-1]
    assert result["status"] == "failed" and result["reading"]["can_continue"] is False
    assert "overlapping" in result["safe_error"]
    assert not worker.run_once(engine)
    assert all(request.purpose != "review" for request in requests)
    assert (await adult.post(f"/api/v1/operations/{result['id']}/retry")).status_code == 409
    assert (
        await adult.post(
            f"/api/v1/problems/{problem['id']}/submissions",
            json={"version": problem["version"], "text": "I rewrote the observation clearly."},
            headers={"Idempotency-Key": str(uuid4())},
        )
    ).status_code == 202
    assert worker.run_once(engine)


@pytest.mark.anyio
async def test_photo_provider_failure_exposes_safe_diagnostic_and_retryability(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_tutor(monkeypatch)
    session = await tutor_session(adult)
    await activity(adult, session)
    assert worker.run_once(engine)
    problem = await latest(adult, session)
    uploaded = await adult.post(
        f"/api/v1/problems/{problem['id']}/photos?version={problem['version']}",
        content=photo_bytes(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert uploaded.status_code == 202

    def reject(_provider: ProviderConfig, _request: ModelRequest) -> ModelResult:
        raise ProviderError("invalid_request")

    monkeypatch.setattr(worker, "complete", reject)
    assert worker.run_once(engine)
    result = (await latest(adult, session))["operations"][-1]
    assert result["status"] == "failed"
    assert result["error_code"] == "invalid_request"
    assert result["retryable"] is False
    assert result["safe_error"] == (
        "The photo reader rejected the request. Ask an adult to check the model and "
        "connection settings. Your work is saved."
    )
    assert (await adult.post(f"/api/v1/operations/{result['id']}/retry")).status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["reference_text", "reference_photo"])
async def test_reference_is_only_for_distinct_generation_never_review(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    original = "ORIGINAL HOMEWORK: Explain why the twelve original plants lost mass."
    requests = install_tutor(monkeypatch, reference=original)
    session = await tutor_session(adult)
    problem = await activity(
        adult,
        session,
        source=source,
        **({"reference_text": original} if source == "reference_text" else {}),
    )
    if source == "reference_photo":
        assert problem["activity_state"] == "reference_capture"
        link = await phone_link(adult, problem)
        async with client(engine) as phone:
            assert (
                await phone.post(
                    "/api/v1/phone-upload/photos",
                    content=photo_bytes(),
                    headers={
                        "X-Photo-Token": link["url"].split("#capture=")[1],
                        "Idempotency-Key": str(uuid4()),
                    },
                )
            ).status_code == 202
        assert worker.run_once(engine)
        assert (await latest(adult, session))["operations"][-1]["status"] == "queued"
    assert worker.run_once(engine)
    generation_request = requests[-1]
    assert generation_request.purpose == "generate" and original in str(
        generation_request.ordered_messages
    )
    problem = await latest(adult, session)
    assert original not in problem["problem_text"]
    result = await adult.post(
        f"/api/v1/problems/{problem['id']}/submissions",
        json={"version": problem["version"], "text": "I compare the seedlings."},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 202
    assert worker.run_once(engine)
    assert requests[-1].purpose == "review"
    assert original not in str(requests[-1].ordered_messages)
    assert "NEVER" in requests[-2].system_instruction


@pytest.mark.anyio
async def test_settings_export_ownership_and_demo_boundaries(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = install_tutor(monkeypatch)
    session = await tutor_session(adult)
    await activity(adult, session)
    assert worker.run_once(engine)
    settings = await adult.post(
        f"/api/v1/tutor/sessions/{session['id']}/settings",
        json={"initiative": "learner_led", "difficulty": "introductory"},
    )
    assert settings.status_code == 200
    assert settings.json()["initiative"] == "learner_led"
    assert settings.json()["difficulty"] == "introductory"
    assert (
        await adult.post(
            f"/api/v1/tutor/sessions/{session['id']}/settings",
            json={"initiative": "solve_everything"},
        )
    ).status_code == 422
    problem = await latest(adult, session)
    assert (
        await adult.post(
            f"/api/v1/problems/{problem['id']}/submissions",
            json={"version": problem["version"], "kind": "hint", "help_level": 4},
            headers={"Idempotency-Key": str(uuid4())},
        )
    ).status_code == 403
    assert (
        await adult.post(
            f"/api/v1/problems/{problem['id']}/submissions",
            json={"version": problem["version"], "kind": "hint", "help_level": 2},
            headers={"Idempotency-Key": str(uuid4())},
        )
    ).status_code == 202
    assert worker.run_once(engine)
    assert "unsolicited" in requests[-1].system_instruction
    assert "Difficulty: easier" in requests[-1].system_instruction
    exported = await adult.post(f"/api/v1/admin/learners/{session['learner_id']}/export")
    assert exported.status_code == 200
    assert exported.json()["sessions"][-1]["topic"] == session["topic"]
    async with client(engine) as stranger:
        assert (await stranger.get(f"/api/v1/tutor/sessions/{session['id']}")).status_code == 401
        assert (
            await stranger.post(
                f"/api/v1/tutor/sessions/{session['id']}/settings", json={"initiative": "balanced"}
            )
        ).status_code == 401
    assert (await adult.get("/api/v1/sessions")).json() == []
    monkeypatch.setenv("APP_MODE", "demo")
    features = (await adult.get(f"/api/v1/learners/{session['learner_id']}/features")).json()
    assert features["tutoring_available"] is False
    assert (
        await adult.post(
            "/api/v1/tutor/sessions",
            json={"learner_id": session["learner_id"], "topic": "History"},
            headers={"Idempotency-Key": str(uuid4())},
        )
    ).status_code == 403


@pytest.mark.anyio
async def test_canceled_photo_stage_and_expired_worker_do_not_resume(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_tutor(monkeypatch)
    session = await tutor_session(adult)
    await activity(adult, session)
    work = worker.claim(engine)
    assert work is not None
    prepared = worker.prepare(engine, work)
    assert prepared is not None
    with Session(engine) as db:
        job = db.get(Job, work.job_id)
        assert job is not None
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    result = ModelResult(
        model_id="fixture-v1",
        validated_payload=ActivityPayload(
            problem_text="This expired worker must not assign this activity.",
            concept_focus="Stale work",
        ),
    )
    assert worker.finish(engine, work, result) is False
    assert (await adult.post(f"/api/v1/operations/{work.submission_id}/cancel")).status_code == 200
    assert not worker.run_once(engine)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(TutorTurn)) == 0
        saved = db.get(PracticeSession, UUID(session["id"]))
        assert saved is not None and saved.status == "open"


@pytest.mark.anyio
async def test_legacy_external_api_cannot_put_homework_in_tutor_session(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_EXTERNAL_PROBLEMS", "true")
    session = await tutor_session(adult)
    response = await adult.post(
        f"/api/v1/sessions/{session['id']}/external-problem",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProblemInstance)) == 0


@pytest.mark.anyio
async def test_copied_assignment_is_not_accepted_as_generated_practice(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = "Explain the exact sequence of events in this supplied homework assignment."
    session = await tutor_session(adult)
    await activity(adult, session, source="reference_text", reference_text=original)

    def copy(_provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        return ModelResult(
            model_id=request.model_id,
            validated_payload=ActivityPayload(
                problem_text=original, concept_focus="Copied homework"
            ),
        )

    monkeypatch.setattr(worker, "complete", copy)
    assert worker.run_once(engine)
    problem = await latest(adult, session)
    assert problem["activity_state"] == "generating"
    assert problem["operations"][-1]["status"] == "failed"
    assert "repeated" in problem["operations"][-1]["safe_error"]
    assert original != problem["problem_text"]


@pytest.mark.anyio
@pytest.mark.parametrize("column,value", [("mode", "anything"), ("initiative", "solve")])
async def test_tutoring_session_database_enforces_allowed_modes(
    adult: AsyncClient, engine: Engine, column: str, value: str
) -> None:
    session = await tutor_session(adult)
    with Session(engine) as db:
        row = db.get(PracticeSession, UUID(session["id"]))
        assert row is not None
        setattr(row, column, value)
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "photo_boundary,text_boundary", [("local_network", "cloud"), ("cloud", "local_network")]
)
async def test_photo_and_text_processing_boundaries_are_separately_visible(
    adult: AsyncClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    photo_boundary: str,
    text_boundary: str,
) -> None:
    from math_tutor import providers

    def route(
        _db: Session, _config: object, stage: str, _learner_id: UUID
    ) -> tuple[str, ProviderConfig]:
        return "synthetic", ProviderConfig.model_validate(
            {
                "adapter": "compatible",
                "model": "synthetic-boundary-test",
                "data_boundary": photo_boundary if stage == "vision" else text_boundary,
            }
        )

    monkeypatch.setattr(providers, "authorize_route", route)
    learner = (await learner_ids(adult))[0]
    features = (await adult.get(f"/api/v1/learners/{learner}/features")).json()
    assert features["text_processing"] == text_boundary
    assert ("cloud provider" if photo_boundary == "cloud" else "private network") in features[
        "photo_status"
    ]
    assert "automatically" in features["photo_status"]


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["reference_text", "reference_photo"])
async def test_reference_export_is_typed_complete_and_adult_only(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    original = (
        "Synthetic original homework reference retained for the learner's authenticated export."
    )
    install_tutor(monkeypatch, reference=original)
    session = await tutor_session(adult)
    problem = await activity(
        adult,
        session,
        source=source,
        **({"reference_text": original} if source == "reference_text" else {}),
    )
    if source == "reference_photo":
        assert (
            await adult.post(
                f"/api/v1/problems/{problem['id']}/photos?version={problem['version']}",
                content=photo_bytes(),
                headers={"Idempotency-Key": str(uuid4())},
            )
        ).status_code == 202
        assert worker.run_once(engine)
    assert worker.run_once(engine)
    url = f"/api/v1/admin/learners/{session['learner_id']}/export"
    response = await adult.post(url)
    assert response.status_code == 200
    assert response.json()["reference_material"] == [
        {"problem_id": problem["id"], "source": source, "text": original}
    ]
    assert all(
        private not in response.json()["reference_material"][0]
        for private in ["parameters", "expected_result", "seed", "request_digest"]
    )
    assert response.headers["Cache-Control"] == "no-store"
    other = (await learner_ids(adult))[1]
    assert (await adult.post(f"/api/v1/admin/learners/{other}/export")).json()[
        "reference_material"
    ] == []
    async with client(engine) as stranger:
        assert (await stranger.post(url)).status_code == 401
        await pair_learner(adult, stranger, session["learner_id"])
        assert (await stranger.post(url)).status_code == 403
