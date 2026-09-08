"""Synthetic encrypted setup, effective routing, authorization, and recovery gates."""

import json
from datetime import timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Any
from uuid import UUID

import pytest
from httpx2 import AsyncClient, Client, MockTransport, Request, Response
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_tutoring import activity, tutor_session
from test_workflows import adult as adult
from test_workflows import anyio_backend as anyio_backend
from test_workflows import client, learner_ids, sign_in_learner
from test_workflows import engine as engine

from math_tutor import worker
from math_tutor.adapters.db.engine import create_engine_for_url
from math_tutor.adapters.db.models import (
    Job,
    ModelCall,
    ProviderConnection,
    ProviderPolicy,
    ProviderProbe,
    ProviderProbeResult,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import Configuration, ProviderConfig, Routes, route
from math_tutor.adapters.providers.contracts import (
    DEFAULT_TUTOR_OUTPUT_LIMIT,
    MAX_CONFIGURED_CONTEXT_LIMIT,
    ModelRequest,
    ModelResult,
    ProviderError,
    ReadingPayload,
)
from math_tutor.adapters.providers.transports import HTTPProvider, MockProvider
from math_tutor.providers import effective_configuration, probe_fingerprint

BASE = "/api/v1/admin/providers"
KEY = "synthetic-provider-key-never-a-real-credential-12345"


def connection(**changes: Any) -> dict[str, Any]:
    return {
        "adapter": "ollama",
        "model": "synthetic-installed-model-v1",
        "base_url": "http://127.0.0.1:11434/api",
        "enabled": True,
        "boundary": "local_network",
        "audience": "mixed",
        "eligibility_record": "Synthetic fixture: adult confirms eligibility for mixed learners.",
        "image_input": True,
        **changes,
    }


async def add(adult: AsyncClient, name: str = "local", **changes: Any) -> None:
    response = await adult.post(BASE + "/connections", json={"id": name, **connection(**changes)})
    assert response.status_code == 201, response.text


def record_probes(engine: Engine, name: str = "local", days_old: int = 0) -> None:
    with Session(engine) as db:
        provider = effective_configuration(db).providers[name]
        for stage in ("tutor", "vision"):
            db.merge(
                ProviderProbe(
                    fingerprint=probe_fingerprint(provider, stage),
                    provider_id=name,
                    stage=stage,
                    tested_at=utcnow() - timedelta(days=days_old),
                )
            )
        db.commit()


@pytest.mark.anyio
async def test_private_connection_lifecycle_encrypts_reopens_and_never_returns_key(
    adult: AsyncClient, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_call(*_args: object) -> None:
        pytest.fail("Saving or reading settings must never contact a provider")

    monkeypatch.setattr("math_tutor.api.providers.complete", no_call)
    await add(adult, api_key_action="replace", api_key=KEY)
    response = await adult.get(BASE)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    data = response.json()
    saved = next(p for p in data["providers"] if p["id"] == "local")
    assert saved["base_url"] == "http://127.0.0.1:11434"
    assert saved["managed"] and saved["key_configured"] and not saved["key_needs_replacement"]
    assert saved["requires_approval"]
    assert not saved["tutor_probed"] and not saved["vision_probed"]
    assert data["routes"] == {"tutor": "demo", "vision": "demo"}
    assert KEY not in response.text and "encrypted_api_key" not in response.text
    exported = await adult.post(f"/api/v1/admin/learners/{(await learner_ids(adult))[0]}/export")
    assert exported.status_code == 200
    assert KEY not in exported.text and "encrypted_api_key" not in exported.text
    assert "base_url" not in exported.text and "credential_revision" not in exported.text
    with Session(engine) as db:
        row = db.get(ProviderConnection, "local")
        assert row is not None and row.encrypted_api_key and KEY not in row.encrypted_api_key
        assert KEY not in json.dumps(row.configuration)
        config = effective_configuration(db)
        assert KEY not in config.model_dump_json() and KEY not in repr(config)
        assert config.providers["local"].api_key_secret is not None
        before = config.fingerprint()
    reopened = create_engine_for_url(str(engine.url))
    try:
        with Session(reopened) as db:
            config = effective_configuration(db)
            assert config.fingerprint() == before
            assert config.providers["local"].api_key_secret is not None
            assert config.providers["local"].api_key_secret.get_secret_value() == KEY
    finally:
        reopened.dispose()
    assert KEY.encode() not in (tmp_path / "work.sqlite3").read_bytes()
    response = await adult.delete(BASE + "/connections/local")
    assert response.status_code == 200
    with Session(engine) as db:
        assert db.get(ProviderConnection, "local") is None


@pytest.mark.anyio
async def test_large_context_limit_is_saved_and_excessive_value_is_rejected(
    adult: AsyncClient, engine: Engine
) -> None:
    await add(adult, "million-context", configured_context_limit=1_000_000)
    saved = next(
        provider
        for provider in (await adult.get(BASE)).json()["providers"]
        if provider["id"] == "million-context"
    )
    assert saved["configured_context_limit"] == 1_000_000
    with Session(engine) as db:
        persisted = db.get(ProviderConnection, "million-context")
        assert persisted is not None
        assert persisted.configuration["capabilities"]["configured_context_limit"] == 1_000_000

    response = await adult.post(
        BASE + "/connections",
        json={
            "id": "excessive-context",
            **connection(configured_context_limit=MAX_CONFIGURED_CONTEXT_LIMIT + 1),
        },
    )
    assert response.status_code == 422
    with Session(engine) as db:
        assert db.get(ProviderConnection, "excessive-context") is None


@pytest.mark.anyio
async def test_meta_mixed_audience_saves_and_routes_without_provider_call(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_call(*_args: object) -> None:
        pytest.fail("Saving and selecting a tested route must not contact the provider")

    monkeypatch.setenv("ALLOW_CLOUD_INFERENCE", "true")
    monkeypatch.setattr("math_tutor.api.providers.complete", no_call)
    eligibility_record = "Synthetic fixture: operator reviewed Meta terms for mixed users."
    await add(
        adult,
        "meta-mixed",
        adapter="meta",
        model="synthetic-meta-model-v1",
        base_url="https://synthetic.meta.invalid/v1",
        boundary="cloud",
        audience="mixed",
        eligibility_record=eligibility_record,
        api_key_action="replace",
        api_key=KEY,
    )
    record_probes(engine, "meta-mixed")
    response = await adult.post(
        BASE + "/routes",
        json={
            "tutor": "meta-mixed",
            "vision": "meta-mixed",
            "acknowledge_data_boundary": True,
        },
    )
    assert response.status_code == 200, response.text
    saved = next(
        provider
        for provider in (await adult.get(BASE)).json()["providers"]
        if provider["id"] == "meta-mixed"
    )
    assert saved["boundary"] == "cloud"
    assert saved["audience"] == "mixed"
    assert saved["eligibility_record"] == eligibility_record
    with Session(engine) as db:
        config = effective_configuration(db)
        assert config.routes == Routes(tutor="meta-mixed", vision="meta-mixed")
        for eligibility in ("adult", "minor", "unknown"):
            assert route(config, "tutor", eligibility)[0] == "meta-mixed"


@pytest.mark.anyio
async def test_key_retention_replacement_endpoint_changes_and_probe_expiry(
    adult: AsyncClient, engine: Engine
) -> None:
    await add(adult, api_key_action="replace", api_key=KEY)
    record_probes(engine)
    with Session(engine) as db:
        before = effective_configuration(db).fingerprint()
    response = await adult.put(
        BASE + "/connections/local", json=connection(base_url="http://localhost:1234")
    )
    assert response.status_code == 422
    with Session(engine) as db:
        assert effective_configuration(db).fingerprint() == before
    changed = connection(api_key_action="replace", api_key=KEY + "-rotated")
    assert (await adult.put(BASE + "/connections/local", json=changed)).status_code == 200
    with Session(engine) as db:
        config = effective_configuration(db)
        assert config.fingerprint() != before
        assert list(db.scalars(select(ProviderProbe))) == []
    record_probes(engine, days_old=8)
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert not saved["tutor_probed"] and not saved["vision_probed"]
    selection = {"tutor": "local", "vision": "local", "acknowledge_data_boundary": True}
    assert (await adult.post(BASE + "/routes", json=selection)).status_code == 422
    record_probes(engine)
    assert (await adult.post(BASE + "/routes", json=selection)).status_code == 200
    assert (await adult.delete(BASE + "/connections/local")).status_code == 409
    assert (
        await adult.put(BASE + "/connections/local", json=connection(api_key_action="remove"))
    ).status_code == 200
    with Session(engine) as db:
        assert effective_configuration(db).providers["local"].api_key_secret is None


@pytest.mark.anyio
async def test_session_secret_rotation_leaves_settings_repairable(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult, api_key_action="replace", api_key=KEY)
    # Session tokens are HMAC-bound to SESSION_SECRET. Restore it for HTTP auth
    # while independently testing the worker's rotated-secret config behavior.
    with monkeypatch.context() as changed:
        changed.setenv("SESSION_SECRET", "different-synthetic-secret-at-least-32-characters")
        with Session(engine) as db:
            config = effective_configuration(db)
            assert config.providers["local"].credential_unavailable
            assert config.providers["local"].api_key_secret is None
    with Session(engine) as db:
        row = db.get(ProviderConnection, "local")
        assert row is not None
        row.encrypted_api_key = "synthetic-damaged-encrypted-value"
        db.commit()
    response = await adult.get(BASE)
    assert response.status_code == 200
    saved = next(p for p in response.json()["providers"] if p["id"] == "local")
    assert saved["key_configured"] and saved["key_needs_replacement"]
    assert (
        await adult.put(
            BASE + "/connections/local", json=connection(api_key_action="replace", api_key=KEY)
        )
    ).status_code == 200
    with Session(engine) as db:
        assert not effective_configuration(db).providers["local"].credential_unavailable


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "http://169.254.169.254/latest/meta-data"},
        {"base_url": "http://metadata.google.internal"},
        {"base_url": "http://[::ffff:169.254.169.254]"},
        {"base_url": "http://localhost:11434?key=" + KEY},
        {"base_url": "https://user:" + KEY + "@example.invalid"},
        {"base_url": "http://127.0.0.1:11434", "boundary": "cloud"},
        {"base_url": "https://8.8.8.8", "boundary": "local_network"},
        {"model": "latest"},
        {"eligibility_record": "   "},
        {"configured_output_limit": 63},
        {"configured_output_limit": 131073},
        {"reasoning_effort": "high"},
        {"reasoning_effort": "none"},
        {"api_key": KEY},
        {"api_key_action": "replace", "api_key": "\n" + KEY},
        {"adapter": "meta", "boundary": "local_network"},
    ],
)
async def test_invalid_connections_fail_without_echoing_input(
    adult: AsyncClient, engine: Engine, change: dict[str, Any]
) -> None:
    response = await adult.post(
        BASE + "/connections", json={"id": "invalid", **connection(**change)}
    )
    assert response.status_code == 422 and KEY not in response.text
    with Session(engine) as db:
        assert db.get(ProviderConnection, "invalid") is None


@pytest.mark.anyio
async def test_connection_authorization_csrf_demo_and_file_route_collision(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"id": "local", **connection()}
    async with client(engine) as guest, client(engine) as child:
        await sign_in_learner(adult, child, (await learner_ids(adult))[0])
        for browser, status in ((guest, 401), (child, 403)):
            assert (await browser.get(BASE)).status_code == status
            assert (await browser.post(BASE + "/connections", json=body)).status_code == status
            assert (
                await browser.put(BASE + "/connections/local", json=connection())
            ).status_code == status
            assert (await browser.delete(BASE + "/connections/local")).status_code == status
            assert (
                await browser.post(
                    BASE + "/policy",
                    json={
                        "allow_cloud_inference": True,
                        "app_audience": "adult_only",
                        "acknowledge_data_boundary": True,
                    },
                )
            ).status_code == status
    assert (
        await adult.post(BASE + "/connections", json=body, headers={"X-CSRF-Token": "wrong"})
    ).status_code == 403
    assert (await adult.post(BASE + "/connections", json={**body, "id": "demo"})).status_code == 409
    assert (await adult.put(BASE + "/connections/demo", json=connection())).status_code == 409
    assert (await adult.delete(BASE + "/connections/demo")).status_code == 409
    monkeypatch.setenv("APP_MODE", "demo")
    assert (await adult.post(BASE + "/connections", json=body)).status_code == 403


@pytest.mark.anyio
async def test_cloud_policy_explicit_consent_env_ceiling_and_audience(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(
        adult,
        "cloud",
        adapter="compatible",
        base_url="https://model.example.invalid/v1",
        boundary="cloud",
        audience="adult_only",
    )
    body = {
        "allow_cloud_inference": True,
        "app_audience": "adult_only",
        "acknowledge_data_boundary": True,
    }
    assert (await adult.post(BASE + "/policy", json=body)).status_code == 409
    monkeypatch.delenv("ALLOW_CLOUD_INFERENCE")
    monkeypatch.delenv("APP_AUDIENCE")
    assert (
        await adult.post(BASE + "/policy", json={**body, "acknowledge_data_boundary": False})
    ).status_code == 422
    with Session(engine) as db:
        config = effective_configuration(db).model_copy(update={"routes": Routes(tutor="cloud")})
        with pytest.raises(ProviderError, match="cloud_disabled"):
            route(config, "tutor", "adult", require_approval=False)
    assert (await adult.post(BASE + "/policy", json=body)).status_code == 200
    with Session(engine) as db:
        config = effective_configuration(db).model_copy(update={"routes": Routes(tutor="cloud")})
        assert route(config, "tutor", "adult", require_approval=False)[0] == "cloud"
        with pytest.raises(ProviderError, match="audience_blocked"):
            route(config, "tutor", "minor", require_approval=False)
        assert db.get(ProviderPolicy, "active") is not None
    monkeypatch.setenv("APP_AUDIENCE", "unknown")
    with Session(engine) as db:
        config = effective_configuration(db).model_copy(update={"routes": Routes(tutor="cloud")})
        with pytest.raises(ProviderError, match="audience_blocked"):
            route(config, "tutor", "adult", require_approval=False)
    policy = (await adult.get(BASE)).json()["policy"]
    assert policy["app_audience"] == "mixed" and policy["audience_locked"]


@pytest.mark.anyio
async def test_worker_refresh_uses_saved_key_and_rejects_pending_work_after_key_change(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult, api_key_action="replace", api_key=KEY)
    record_probes(engine)
    assert (
        await adult.post(
            BASE + "/routes",
            json={"tutor": "local", "vision": "local", "acknowledge_data_boundary": True},
        )
    ).status_code == 200
    seen: list[str] = []

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        assert provider.api_key_secret is not None
        seen.append(provider.api_key_secret.get_secret_value())
        return MockProvider().complete(request)

    monkeypatch.setattr(worker, "complete", complete)
    session = await tutor_session(adult)
    await activity(adult, session)
    assert worker.run_once(engine)
    assert seen == [KEY]
    second = await tutor_session(adult)
    work = await activity(adult, second)
    assert (
        await adult.put(
            BASE + "/connections/local",
            json=connection(api_key_action="replace", api_key=KEY + "-new"),
        )
    ).status_code == 200
    record_probes(engine)
    assert worker.run_once(engine)
    assert seen == [KEY]  # no replay of already authorized work to changed credentials
    with Session(engine) as db:
        job = db.scalar(select(Job).where(Job.submission_id == UUID(work["operations"][0]["id"])))
        assert job is not None and job.state == "failed"
    assert (
        await adult.post(
            BASE + "/routes",
            json={"tutor": "local", "vision": "local", "acknowledge_data_boundary": True},
        )
    ).status_code == 200
    third = await tutor_session(adult)
    await activity(adult, third)
    assert worker.run_once(engine)
    assert seen == [KEY, KEY + "-new"]


@pytest.mark.anyio
async def test_current_schema_probes_require_explicit_consent_and_do_not_activate_routes(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult, api_key_action="replace", api_key=KEY)
    calls: list[ModelRequest] = []

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        calls.append(request)
        assert request.timeout_seconds <= 90
        assert provider.api_key_secret is not None
        if request.stage == "vision":
            assert request.purpose == "read" and request.private_image_bytes
            return ModelResult(
                model_id=request.model_id,
                validated_payload=ReadingPayload(
                    transcription="1/2",
                    quality="clear",
                    confidence=0.95,
                    ambiguities=[],
                    organization_feedback=[],
                    rejection_reason=None,
                ),
            )
        return MockProvider().complete(request)

    monkeypatch.setattr("math_tutor.api.providers.complete", complete)
    assert (await adult.post(BASE + "/local/probe", json={"stage": "tutor"})).status_code == 422
    assert not calls
    for stage in ("tutor", "vision"):
        response = await adult.post(
            BASE + "/local/probe", json={"stage": stage, "authorize_synthetic_call": True}
        )
        assert response.status_code == 200, response.text
    assert [request.purpose for request in calls] == ["generate", "review", "read"]
    assert [request.response_schema["title"] for request in calls] == [
        "ActivityPayload",
        "FeedbackPayload",
        "ReadingPayload",
    ]
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["tutor_probed"] and saved["vision_probed"] and saved["requires_approval"]
    with Session(engine) as db:
        config = effective_configuration(db).model_copy(update={"routes": Routes(tutor="local")})
        with pytest.raises(ProviderError, match="approval_required"):
            route(config, "tutor", "adult")
    assert (
        await adult.post(
            BASE + "/routes",
            json={"tutor": "local", "vision": "local", "acknowledge_data_boundary": True},
        )
    ).status_code == 200
    with Session(engine) as db:
        assert not effective_configuration(db).providers["local"].requires_approval


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("finish_reason", "code"),
    [
        ("length", "output_limit"),
        ("tool_calls", "incomplete_output"),
        ("content_filter", "refusal"),
    ],
)
async def test_photo_pass_survives_incomplete_tutor_with_safe_step_diagnostics(
    adult: AsyncClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    finish_reason: str,
    code: str,
) -> None:
    await add(adult, adapter="compatible", base_url="http://127.0.0.1:8081/v1")
    calls: list[dict[str, Any]] = []
    fail_review = True

    def respond(request: Request) -> Response:
        wire = json.loads(request.content)
        calls.append(wire)
        properties = wire["response_format"]["json_schema"]["schema"]["properties"]
        if "transcription" in properties:
            assert wire["messages"][-1]["content"][1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
            payload = {
                "transcription": "1/2",
                "quality": "clear",
                "confidence": 1,
                "ambiguities": [],
                "organization_feedback": [],
                "rejection_reason": None,
            }
        else:
            assert wire["max_tokens"] == DEFAULT_TUTOR_OUTPUT_LIMIT == 16384
            if "strengths" in properties and fail_review:
                return Response(
                    200,
                    json={
                        "choices": [{"finish_reason": finish_reason, "message": {"content": KEY}}]
                    },
                )
            payload = (
                {"problem_text": "Compare observations of two plants.", "concept_focus": "Evidence"}
                if "problem_text" in properties
                else {
                    "strengths": [],
                    "guidance": ["Explain your observation."],
                    "next_step": "Name one observation.",
                    "concepts": [],
                    "uncertainty_note": None,
                }
            )
        return Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}]
            },
        )

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        with Client(transport=MockTransport(respond)) as transport:
            return HTTPProvider(provider, transport).complete(request)

    monkeypatch.setattr("math_tutor.api.providers.complete", complete)
    consent = {"authorize_synthetic_call": True}
    assert (
        await adult.post(BASE + "/local/probe", json={**consent, "stage": "vision"})
    ).status_code == 200
    response = await adult.post(BASE + "/local/probe", json={**consent, "stage": "tutor"})
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert response.json()["probe_step"] == "review"
    assert KEY not in response.text
    assert len(calls) == 3  # One image, activity, incomplete feedback; no automatic retry.
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["vision_probed"] and not saved["tutor_probed"]
    latest = saved["recent_tests"][0]
    assert latest["status"] == "failed" and latest["code"] == code
    assert latest["http_status"] == 422 and latest["step"] == "review"
    if code != "refusal":
        assert latest["completion_reason"] == finish_reason
    assert latest["requests_started"] == 2 and latest["output_limit"] == 16384
    assert latest["elapsed_ms"] >= 0
    assert KEY not in json.dumps(saved["recent_tests"])
    with Session(engine) as db:
        assert [p.stage for p in db.scalars(select(ProviderProbe))] == ["vision"]
    fail_review = False
    assert (
        await adult.post(BASE + "/local/probe", json={**consent, "stage": "tutor"})
    ).status_code == 200
    assert len(calls) == 5


@pytest.mark.anyio
async def test_probe_diagnostics_do_not_upgrade_a_stale_read_snapshot(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult)
    committed = Event()
    errors: list[Exception] = []

    def other_writer() -> None:
        try:
            with Session(engine) as db:
                db.add(ProviderProbe(fingerprint="b" * 64, provider_id="unrelated", stage="vision"))
                db.commit()
        except Exception as error:
            errors.append(error)
        finally:
            committed.set()

    writer = Thread(target=other_writer)
    reads = 0

    def read_configuration(db: Session) -> Configuration:
        nonlocal reads
        result = effective_configuration(db)
        reads += 1
        if reads == 2:
            # Another worker writes after this probe revalidates its policy.
            # A deferred read snapshot would become stale; an immediate
            # transaction makes that writer wait until diagnostic commit.
            writer.start()
            committed.wait(0.5)
        return result

    monkeypatch.setattr("math_tutor.api.providers.effective_configuration", read_configuration)
    monkeypatch.setattr(
        "math_tutor.api.providers.complete",
        lambda provider, request: MockProvider().complete(request),
    )
    try:
        result = await adult.post(
            BASE + "/local/probe",
            json={"stage": "tutor", "authorize_synthetic_call": True},
        )
        assert result.status_code == 200, result.text
    finally:
        if writer.ident is not None:
            writer.join(timeout=5)
    assert committed.is_set() and not errors
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["recent_tests"][0]["status"] == "passed"
    assert saved["recent_tests"][0]["requests_started"] == 2


@pytest.mark.anyio
async def test_provider_http_failure_status_survives_safe_probe_translation(
    adult: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult)

    def reject(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        raise ProviderError("authentication", http_status=401)

    monkeypatch.setattr("math_tutor.api.providers.complete", reject)
    result = await adult.post(
        BASE + "/local/probe",
        json={"stage": "tutor", "authorize_synthetic_call": True},
    )
    assert result.status_code == 422 and result.json()["code"] == "authentication"
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["recent_tests"][0]["http_status"] == 401


@pytest.mark.anyio
async def test_meta_effort_persists_reaches_probes_and_worker_and_invalidates_readiness(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOW_CLOUD_INFERENCE", "true")
    body = connection(
        adapter="meta",
        base_url="https://synthetic.invalid/v1",
        boundary="cloud",
        api_key_action="replace",
        api_key=KEY,
        reasoning_effort="high",
    )
    await add(adult, **body)
    purposes: list[str] = []

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        assert provider.capabilities.reasoning_effort == "high"
        assert request.max_output_tokens == 16384
        purposes.append(request.purpose)
        if request.purpose == "read":
            return ModelResult(
                model_id=request.model_id,
                validated_payload=ReadingPayload(
                    transcription="1/2",
                    quality="clear",
                    confidence=1,
                    ambiguities=[],
                    organization_feedback=[],
                    rejection_reason=None,
                ),
            )
        return MockProvider().complete(request)

    monkeypatch.setattr("math_tutor.api.providers.complete", complete)
    monkeypatch.setattr(worker, "complete", complete)
    for stage in ("tutor", "vision"):
        response = await adult.post(
            BASE + "/local/probe", json={"stage": stage, "authorize_synthetic_call": True}
        )
        assert response.status_code == 200, response.text
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["reasoning_effort"] == "high"
    assert all(
        test["reasoning_effort"] == "high" and test["output_limit"] == 16384
        for test in saved["recent_tests"]
    )
    roles = {"tutor": "local", "vision": "local", "acknowledge_data_boundary": True}
    assert (await adult.post(BASE + "/routes", json=roles)).status_code == 200
    await activity(adult, await tutor_session(adult))
    assert worker.run_once(engine)
    assert purposes == ["generate", "review", "read", "generate"]
    with Session(engine) as db:
        call = db.scalar(select(ModelCall).where(ModelCall.provider_id == "local"))
        assert call is not None and call.reasoning_effort == "high"
    body.pop("api_key")
    body.update(api_key_action="keep", reasoning_effort="low")
    assert (await adult.put(BASE + "/connections/local", json=body)).status_code == 200
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["reasoning_effort"] == "low"
    assert not saved["tutor_probed"] and not saved["vision_probed"]
    assert saved["recent_tests"][0]["reasoning_effort"] == "high"
    assert (await adult.post(BASE + "/routes", json=roles)).status_code == 422


@pytest.mark.anyio
async def test_test_history_is_bounded_expires_and_is_deleted_with_connection(
    adult: AsyncClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from math_tutor.retention import sweep

    await add(adult, configured_output_limit=24576, configured_context_limit=100000)

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        assert request.max_output_tokens == 24576
        return MockProvider().complete(request)

    monkeypatch.setattr("math_tutor.api.providers.complete", complete)
    with Session(engine) as db:
        for index in range(25):
            db.add(
                ProviderProbeResult(
                    provider_id="local",
                    stage="tutor",
                    status="failed",
                    code="incomplete_output",
                    output_limit=1200,
                    requests_started=1,
                    elapsed_ms=100,
                    created_at=utcnow() - timedelta(minutes=index + 1),
                )
            )
        db.commit()
    assert (
        await adult.post(
            BASE + "/local/probe", json={"stage": "tutor", "authorize_synthetic_call": True}
        )
    ).status_code == 200
    with Session(engine) as db:
        results = list(db.scalars(select(ProviderProbeResult)))
        assert len(results) == 20
        for result in results:
            result.created_at = utcnow() - timedelta(days=8)
        db.commit()
    saved = next(p for p in (await adult.get(BASE)).json()["providers"] if p["id"] == "local")
    assert saved["recent_tests"] == []
    sweep(engine)
    with Session(engine) as db:
        assert list(db.scalars(select(ProviderProbeResult))) == []
    assert (
        await adult.post(
            BASE + "/local/probe", json={"stage": "tutor", "authorize_synthetic_call": True}
        )
    ).status_code == 200
    assert (await adult.delete(BASE + "/connections/local")).status_code == 200
    with Session(engine) as db:
        assert list(db.scalars(select(ProviderProbeResult))) == []


@pytest.mark.anyio
async def test_edit_selected_local_to_cloud_requires_fresh_learner_data_consent(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(adult)
    record_probes(engine)
    roles = {"tutor": "local", "vision": "local", "acknowledge_data_boundary": True}
    assert (await adult.post(BASE + "/routes", json=roles)).status_code == 200
    monkeypatch.delenv("ALLOW_CLOUD_INFERENCE")
    assert (
        await adult.post(
            BASE + "/policy",
            json={
                "allow_cloud_inference": True,
                "app_audience": "mixed",
                "acknowledge_data_boundary": True,
            },
        )
    ).status_code == 200
    assert (
        await adult.put(
            BASE + "/connections/local",
            json=connection(boundary="cloud", base_url="https://synthetic.example.invalid/v1"),
        )
    ).status_code == 200
    record_probes(engine)  # Even successful synthetic tests cannot approve learner transfers.
    with Session(engine) as db, pytest.raises(ProviderError, match="approval_required"):
        route(effective_configuration(db), "tutor", "adult")
    assert (
        await adult.post(BASE + "/routes", json={**roles, "acknowledge_data_boundary": False})
    ).status_code == 422
    assert (await adult.post(BASE + "/routes", json=roles)).status_code == 200
    with Session(engine) as db:
        assert route(effective_configuration(db), "tutor", "adult")[1].data_boundary == "cloud"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    ["second_schema", "late_change", "deleted", "authentication", "uncertain_photo", "unsafe_code"],
)
async def test_failed_or_stale_probe_does_not_record_success(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    await add(adult)
    calls = 0

    def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        if failure == "authentication":
            raise ProviderError("authentication", safe_message="vendor accidentally echoed " + KEY)
        if failure == "unsafe_code":
            raise ProviderError(KEY, safe_message=KEY, completion_reason=KEY)
        if failure == "deleted" and calls == 1:
            with Session(engine) as db:
                row = db.get(ProviderConnection, "local")
                assert row is not None
                db.delete(row)
                for attempt in db.scalars(select(ProviderProbeResult)):
                    db.delete(attempt)
                db.commit()
        if failure == "late_change" and calls == 1:
            with Session(engine) as db:
                row = db.get(ProviderConnection, "local")
                assert row is not None
                row.credential_revision = "synthetic-changed-during-probe"
                db.commit()
        if failure == "uncertain_photo":
            return ModelResult(
                model_id=request.model_id,
                validated_payload=ReadingPayload(
                    transcription="1/2",
                    quality="uncertain",
                    confidence=0.2,
                    ambiguities=["blur"],
                    organization_feedback=[],
                    rejection_reason="Synthetic uncertainty",
                ),
            )
        if failure == "second_schema" and calls == 2:
            return MockProvider().complete(request.model_copy(update={"purpose": "generate"}))
        return MockProvider().complete(request)

    monkeypatch.setattr("math_tutor.api.providers.complete", complete)
    response = await adult.post(
        BASE + "/local/probe",
        json={
            "stage": "vision" if failure == "uncertain_photo" else "tutor",
            "authorize_synthetic_call": True,
        },
    )
    assert response.status_code == (409 if failure in {"late_change", "deleted"} else 422)
    assert KEY not in response.text
    if failure == "authentication":
        assert "API key" in response.text
        assert response.json()["code"] == "authentication"
    if failure == "uncertain_photo":
        assert response.json()["code"] == "probe_reading_failed"
    if failure == "late_change":
        assert calls == 1  # Every provider call revalidates the current policy.
    with Session(engine) as db:
        assert list(db.scalars(select(ProviderProbe))) == []
        results = list(db.scalars(select(ProviderProbeResult)))
        if failure == "deleted":
            assert not results
        else:
            assert len(results) == 1 and results[0].status == "failed"
            assert KEY not in (results[0].code or "")
            assert KEY not in (results[0].completion_reason or "")


@pytest.mark.anyio
async def test_role_approval_rolls_back_if_other_selected_stage_is_untested(
    adult: AsyncClient, engine: Engine
) -> None:
    await add(adult)
    with Session(engine) as db:
        config = effective_configuration(db)
        db.add(
            ProviderProbe(
                fingerprint=probe_fingerprint(config.providers["local"], "tutor"),
                provider_id="local",
                stage="tutor",
            )
        )
        db.commit()
    response = await adult.post(
        BASE + "/routes",
        json={"tutor": "local", "vision": "local", "acknowledge_data_boundary": True},
    )
    assert response.status_code == 422
    with Session(engine) as db:
        config = effective_configuration(db)
        assert config.providers["local"].requires_approval
        assert config.routes == Routes()


@pytest.mark.anyio
async def test_ciphertext_is_bound_to_connection_and_missing_key_never_used(
    adult: AsyncClient, engine: Engine
) -> None:
    await add(adult, "first", api_key_action="replace", api_key=KEY)
    await add(adult, "second", api_key_action="replace", api_key=KEY)
    with Session(engine) as db:
        first, second = db.get(ProviderConnection, "first"), db.get(ProviderConnection, "second")
        assert first is not None and second is not None
        assert first.encrypted_api_key != second.encrypted_api_key
        second.encrypted_api_key = first.encrypted_api_key
        db.commit()
    with Session(engine) as db:
        config = effective_configuration(db)
        assert not config.providers["first"].credential_unavailable
        assert config.providers["second"].credential_unavailable
        assert config.providers["second"].api_key_secret is None


def test_connection_and_policy_transaction_rollback(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(
            ProviderConnection(
                id="rolled-back",
                configuration={},
                encrypted_api_key=None,
                credential_revision="synthetic",
            )
        )
        db.add(ProviderPolicy(name="active", allow_cloud_inference=True, app_audience="adult_only"))
        db.flush()
        db.rollback()
    with Session(engine) as db:
        assert db.get(ProviderConnection, "rolled-back") is None
        assert db.get(ProviderPolicy, "active") is None


@pytest.mark.anyio
async def test_unchanged_connection_save_preserves_approval_and_tests(
    adult: AsyncClient, engine: Engine
) -> None:
    await add(adult, api_key_action="replace", api_key=KEY)
    record_probes(engine)
    roles = {"tutor": "local", "vision": "local", "acknowledge_data_boundary": True}
    assert (await adult.post(BASE + "/routes", json=roles)).status_code == 200
    with Session(engine) as db:
        before = effective_configuration(db).fingerprint()
    assert (await adult.put(BASE + "/connections/local", json=connection())).status_code == 200
    with Session(engine) as db:
        config = effective_configuration(db)
        assert config.fingerprint() == before
        assert not config.providers["local"].requires_approval
        assert len(list(db.scalars(select(ProviderProbe)))) == 2
    assert (
        await adult.put(BASE + "/connections/local", json=connection(model="changed-model"))
    ).status_code == 200
    with Session(engine) as db:
        assert effective_configuration(db).providers["local"].requires_approval
        assert list(db.scalars(select(ProviderProbe))) == []
