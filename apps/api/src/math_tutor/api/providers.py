"""Adult-only redacted provider setup and explicitly requested synthetic probes."""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from math_tutor.adapters.db.models import (
    ModelCall,
    ProviderConnection,
    ProviderProbe,
    ProviderProbeResult,
    RouteSelection,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.images import normalize
from math_tutor.adapters.providers.config import ProviderConfig, Routes, route
from math_tutor.adapters.providers.contracts import (
    DEFAULT_TUTOR_OUTPUT_LIMIT,
    ActivityPayload,
    FeedbackPayload,
    Message,
    ModelRequest,
    ProviderError,
    ReadingPayload,
    ReasoningEffort,
)
from math_tutor.api.access import Adult, Database, principal
from math_tutor.api.learners import Acknowledged
from math_tutor.api.provider_connections import ProviderPolicyPublic
from math_tutor.api.provider_connections import router as connections_router
from math_tutor.providers import (
    complete,
    effective_configuration,
    probe_fingerprint,
    probe_is_current,
)
from math_tutor.tutoring import can_read

router = APIRouter(prefix="/api/v1/admin", tags=["provider administration"])
router.include_router(connections_router)


class ProbeResultPublic(BaseModel):
    stage: Literal["tutor", "vision"]
    status: Literal["running", "passed", "failed"]
    step: Literal["generate", "review", "read"] | None
    code: str | None
    completion_reason: str | None
    http_status: int | None
    output_limit: int
    reasoning_effort: ReasoningEffort = "default"
    requests_started: int
    elapsed_ms: int
    created_at: datetime


class ProviderPublic(BaseModel):
    id: str
    adapter: str
    model: str
    enabled: bool
    boundary: str
    audience: str
    image_input: bool
    tutor_probed: bool
    vision_probed: bool
    managed: bool = False
    base_url: str | None = None
    key_configured: bool = False
    key_needs_replacement: bool = False
    eligibility_record: str = ""
    configured_context_limit: int = 8192
    configured_output_limit: int = DEFAULT_TUTOR_OUTPUT_LIMIT
    reasoning_effort: ReasoningEffort = "default"
    structured_output_mode: Literal["native", "json_prompt"] = "native"
    requires_approval: bool = False
    recent_tests: list[ProbeResultPublic] = Field(default_factory=list)


class ProvidersPublic(BaseModel):
    routes: Routes
    providers: list[ProviderPublic]
    policy: ProviderPolicyPublic


class ProbeInput(BaseModel):
    stage: Literal["tutor", "vision"]
    authorize_synthetic_call: bool = False


class ProbeFailurePublic(BaseModel):
    detail: str
    code: str
    completion_reason: str | None = None
    probe_step: Literal["generate", "review", "read"] | None = None


@dataclass
class ProbeFailure(ProviderError):
    probe_step: Literal["generate", "review", "read"] | None = None


class SelectRoutes(Routes):
    acknowledge_data_boundary: bool


@router.get("/providers", response_model=ProvidersPublic)
def providers(db: Database, actor: Adult) -> ProvidersPublic:
    config = effective_configuration(db)
    managed_ids = set(db.scalars(select(ProviderConnection.id)))
    return ProvidersPublic(
        routes=config.routes,
        policy=ProviderPolicyPublic(
            allow_cloud_inference=bool(config.allow_cloud_inference),
            app_audience="adult_only" if config.app_audience == "adult_only" else "mixed",
            cloud_locked="ALLOW_CLOUD_INFERENCE" in os.environ,
            audience_locked="APP_AUDIENCE" in os.environ,
            demo_mode=os.getenv("APP_MODE", "private") == "demo",
        ),
        providers=[
            ProviderPublic(
                id=name,
                adapter=p.adapter,
                model=p.model,
                enabled=p.enabled,
                boundary=p.data_boundary,
                audience=p.audience,
                image_input=p.capabilities.image_input,
                tutor_probed=probe_is_current(db, p, "tutor"),
                vision_probed=probe_is_current(db, p, "vision"),
                managed=name in managed_ids,
                base_url=p.base_url,
                key_configured=bool(
                    p.api_key_secret
                    or p.credential_unavailable
                    or (p.api_key_env and os.getenv(p.api_key_env))
                ),
                key_needs_replacement=p.credential_unavailable,
                eligibility_record=p.eligibility_record,
                configured_context_limit=p.capabilities.configured_context_limit,
                configured_output_limit=p.capabilities.configured_output_limit,
                reasoning_effort=p.capabilities.reasoning_effort,
                structured_output_mode=p.capabilities.structured_output_mode,
                requires_approval=p.requires_approval,
                recent_tests=[
                    ProbeResultPublic.model_validate(result, from_attributes=True)
                    for result in db.scalars(
                        select(ProviderProbeResult)
                        .where(
                            ProviderProbeResult.provider_id == name,
                            ProviderProbeResult.created_at >= utcnow() - timedelta(days=7),
                        )
                        .order_by(ProviderProbeResult.created_at.desc())
                        .limit(10)
                    )
                ],
            )
            for name, p in config.providers.items()
        ],
    )


@router.post("/providers/routes", response_model=Acknowledged)
def select_routes(body: SelectRoutes, db: Database, actor: Adult) -> Acknowledged:
    if not body.acknowledge_data_boundary:
        raise HTTPException(422, "Acknowledge the selected data boundary.")
    config = effective_configuration(db)
    routes = Routes(tutor=body.tutor, vision=body.vision)
    updated = config.model_copy(update={"routes": routes})
    for stage in ("tutor", "vision"):
        name, provider = route(updated, stage, "adult", require_approval=False)
        if provider.credential_unavailable or not probe_is_current(db, provider, stage):
            raise HTTPException(
                422,
                "Test the selected tutor and photo reader before saving their roles. Tests expire after seven days.",
            )
        connection = db.get(ProviderConnection, name)
        if connection is not None:
            connection.configuration = {
                **connection.configuration,
                "requires_approval": False,
            }
    row = db.get(RouteSelection, "active")
    if row is None:
        db.add(RouteSelection(name="active", routes=routes.model_dump()))
    else:
        row.routes = routes.model_dump()
    return Acknowledged()


def probe_requests(
    provider: ProviderConfig, stage: Literal["tutor", "vision"]
) -> list[ModelRequest]:
    if stage == "vision":
        image = Image.new("RGB", (256, 128), "white")
        ImageDraw.Draw(image).text((30, 40), "1/2", fill="black", font_size=40)
        output = BytesIO()
        image.save(output, "PNG")
        normalized = normalize(output.getvalue())
        return [
            ModelRequest(
                operation_id=uuid4(),
                stage="vision",
                purpose="read",
                model_id=provider.model,
                system_instruction="Transcribe the visible fraction. Report readability and uncertainty honestly. Return the required reading JSON.",
                ordered_messages=[
                    Message(
                        role="user",
                        content="Read only the visible fraction in this synthetic image.",
                    )
                ],
                private_image_bytes=normalized,
                response_schema=ReadingPayload.model_json_schema(),
                max_output_tokens=provider.capabilities.configured_output_limit,
            )
        ]
    return [
        ModelRequest(
            operation_id=uuid4(),
            stage="tutor",
            purpose="generate",
            model_id=provider.model,
            system_instruction="Create one short original science practice activity about observations and evidence. Do not include its answer. Return the required activity JSON.",
            ordered_messages=[
                Message(
                    role="user",
                    content="Synthetic setup test: practice comparing plant observations.",
                )
            ],
            response_schema=ActivityPayload.model_json_schema(),
            max_output_tokens=provider.capabilities.configured_output_limit,
        ),
        ModelRequest(
            operation_id=uuid4(),
            stage="tutor",
            purpose="review",
            model_id=provider.model,
            system_instruction="Guide a learner to explain their evidence. Do not solve their activity or assign a grade. Return the required feedback JSON.",
            ordered_messages=[
                Message(
                    role="user",
                    content="Synthetic activity: compare two seedlings grown with different light. Synthetic response: I would record their heights each day to see what changes.",
                )
            ],
            response_schema=FeedbackPayload.model_json_schema(),
            max_output_tokens=provider.capabilities.configured_output_limit,
        ),
    ]


def probe_error(
    error: ProviderError,
    step: Literal["generate", "review", "read"] | None = None,
) -> ProbeFailure:
    details = {
        "unavailable": "Cannot reach the model server. Check its URL, that it is running, and this app server's network access.",
        "timeout": "The model test timed out. Check the server and model are running; try a smaller model or a faster server.",
        "authentication": "The model server rejected or could not unlock the API key. Check or replace the key in this connection.",
        "invalid_request": "The server rejected the test request. Check the model name, provider type, and structured-output setting.",
        "malformed_output": "The model did not return the required tutoring format. Check the model and structured-output setting, then test again.",
        "context_limit": "The configured context limit is too small for the tutoring format. Match it to the model server's supported context size.",
        "cloud_disabled": "Cloud calls are disabled. Open App permissions and allow cloud AI before testing this connection.",
        "audience_blocked": "This connection's Allowed users setting does not match who uses the app. Review the connection and App permissions before testing.",
        "invalid_endpoint": "This URL is blocked or resolves outside its declared network boundary. Check the server URL and local/cloud setting.",
        "unsupported_modality": "This connection does not support the selected test. Enable photo reading only for a vision-capable model.",
        "throttled": "The model server is rate-limiting requests. Wait, then test again.",
        "output_limit": "The model reached the response token limit before finishing. Increase Model response limit under Advanced connection options. The provider may charge for the incomplete response.",
        "incomplete_output": "The model stopped without a complete response. The provider may charge even though the test did not pass.",
        "refusal": "The model declined the synthetic request. The test did not pass; no automatic retry was made.",
        "adapter_failure": "The app could not process the model server's response. This is an adapter error; the provider may have completed and charged for the request.",
        "configuration_conflict": "A saved connection conflicts with the server configuration.",
        "route_disabled": "This connection is disabled.",
        "probe_reading_failed": "The model could not clearly read the known test fraction.",
    }
    return ProbeFailure(
        error.code if error.code in details else "provider_error",
        safe_message=details.get(
            error.code,
            "The model test failed. Check the connection and model settings, then retry.",
        ),
        probe_step=step,
        http_status=error.http_status,
        completion_reason=(
            error.completion_reason
            if error.completion_reason
            in {
                "length",
                "max_tokens",
                "tool_calls",
                "function_call",
                "content_filter",
                "stop",
                "end_turn",
                "stop_sequence",
                "missing",
                None,
            }
            else "other"
        ),
    )


@router.post(
    "/providers/{provider_id}/probe",
    response_model=Acknowledged,
    responses={422: {"model": ProbeFailurePublic}},
)
def probe(
    provider_id: str, body: ProbeInput, request: Request, db: Database, actor: Adult
) -> Acknowledged:
    config = effective_configuration(db)
    original_digest = config.fingerprint()
    selected = config.model_copy(update={"routes": Routes(tutor=provider_id, vision=provider_id)})
    try:
        name, provider = route(selected, body.stage, "adult", require_approval=False)
    except ProviderError as error:
        raise probe_error(error) from None
    if provider.adapter != "mock" and not body.authorize_synthetic_call:
        raise HTTPException(422, "Explicit synthetic-call authorization is required.")
    # Start a durable record before inference. A process crash leaves "running"
    # evidence rather than inventing a success or replaying a charged request.
    keep = (
        select(ProviderProbeResult.id)
        .where(ProviderProbeResult.provider_id == name)
        .order_by(ProviderProbeResult.created_at.desc())
        .limit(19)
    )
    db.execute(
        delete(ProviderProbeResult).where(
            ProviderProbeResult.provider_id == name,
            ProviderProbeResult.id.not_in(keep),
        )
    )
    attempt = ProviderProbeResult(
        provider_id=name,
        stage=body.stage,
        status="running",
        output_limit=provider.capabilities.configured_output_limit,
        reasoning_effort=provider.capabilities.reasoning_effort,
        requests_started=0,
        elapsed_ms=0,
    )
    db.add(attempt)
    db.commit()
    attempt_id = attempt.id
    started = time.monotonic()
    try:
        result = run_probe(body, request, db, provider, name, original_digest, attempt)
    except (ProviderError, HTTPException) as error:
        code = (
            probe_error(error).code
            if isinstance(error, ProviderError)
            else ("configuration_changed" if error.status_code == 409 else "authorization_changed")
        )
        db.rollback()
        # A connection may have been deleted during inference. Update only the
        # existing record; never recreate deleted diagnostics or mask the 409.
        db.execute(
            update(ProviderProbeResult)
            .where(ProviderProbeResult.id == attempt_id)
            .values(
                status="failed",
                code=code,
                completion_reason=probe_error(error).completion_reason
                if isinstance(error, ProviderError)
                else None,
                http_status=(error.http_status or 422)
                if isinstance(error, ProviderError)
                else error.status_code,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        )
        db.commit()  # Retain failure even though the request transaction rolls back.
        raise
    attempt.status = "passed"
    attempt.http_status = 200
    attempt.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def run_probe(
    body: ProbeInput,
    request: Request,
    db: Database,
    provider: ProviderConfig,
    name: str,
    original_digest: str,
    attempt: ProviderProbeResult,
) -> Acknowledged:
    deadline = time.monotonic() + 180
    for model_request in probe_requests(provider, body.stage):
        step: Literal["generate", "review", "read"] = (
            "read"
            if body.stage == "vision"
            else "generate"
            if model_request.purpose == "generate"
            else "review"
        )
        # Revalidation and its diagnostic update are one short write
        # transaction. A worker heartbeat between a deferred SELECT and UPDATE
        # otherwise invalidates the SQLite read snapshot (HTTP 503).
        db.connection(execution_options={"sqlite_begin_immediate": True})
        db.expire_all()
        if principal(request, db).role != "adult":
            raise HTTPException(403, "Adult access required.")
        if effective_configuration(db).fingerprint() != original_digest:
            raise HTTPException(
                409,
                "Connection or data policy changed during the test. Test the current settings again.",
            )
        remaining = int(deadline - time.monotonic())
        if remaining < 1:
            raise probe_error(ProviderError("timeout"), step)
        model_request = model_request.model_copy(update={"timeout_seconds": min(90, remaining)})
        attempt.step = step
        attempt.requests_started += 1
        db.commit()  # No database lock is held while the model is running.
        try:
            result = complete(provider, model_request)
        except ProviderError as error:
            raise probe_error(error, step) from None
        payload = result.validated_payload
        if model_request.purpose == "generate" and not isinstance(payload, ActivityPayload):
            raise probe_error(ProviderError("malformed_output"), step)
        if model_request.purpose == "review" and not isinstance(payload, FeedbackPayload):
            raise probe_error(ProviderError("malformed_output"), step)
        if model_request.purpose == "read" and (
            not isinstance(payload, ReadingPayload)
            or (
                provider.adapter != "mock"
                and (not can_read(payload) or payload.transcription.strip() != "1/2")
            )
        ):
            raise ProviderError(
                "probe_reading_failed",
                safe_message="The photo test did not clearly read the known fraction. Check the vision model and its settings.",
            )
    if time.monotonic() > deadline:
        raise probe_error(ProviderError("timeout"))
    db.connection(execution_options={"sqlite_begin_immediate": True})
    db.expire_all()
    current = principal(request, db)
    if current.role != "adult":
        raise HTTPException(403, "Adult access required.")
    if effective_configuration(db).fingerprint() != original_digest:
        raise HTTPException(
            409,
            "Connection or data policy changed during the test. Test the current settings again.",
        )
    fingerprint = probe_fingerprint(provider, body.stage)
    old = db.get(ProviderProbe, fingerprint)
    if old:
        old.tested_at = utcnow()
    else:
        db.add(ProviderProbe(fingerprint=fingerprint, provider_id=name, stage=body.stage))
    return Acknowledged()


class UsagePublic(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: None = None
    cost_status: str = "unknown; no dated pricing configuration"


@router.get("/usage", response_model=UsagePublic)
def usage(db: Database, actor: Adult) -> UsagePublic:
    calls = list(db.scalars(select(ModelCall).order_by(ModelCall.created_at.desc()).limit(10000)))
    return UsagePublic(
        calls=len(calls),
        input_tokens=sum(
            int(
                c.usage.get(
                    "inputTokens", c.usage.get("prompt_tokens", c.usage.get("prompt_eval_count", 0))
                )
            )
            for c in calls
        ),
        output_tokens=sum(
            int(
                c.usage.get(
                    "outputTokens", c.usage.get("completion_tokens", c.usage.get("eval_count", 0))
                )
            )
            for c in calls
        ),
    )
