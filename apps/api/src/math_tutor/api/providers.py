"""Adult-only redacted provider setup and explicitly requested synthetic probes."""

import os
import time
from io import BytesIO
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from PIL import Image, ImageDraw
from pydantic import BaseModel
from sqlalchemy import select

from math_tutor.adapters.db.models import (
    ModelCall,
    ProviderConnection,
    ProviderProbe,
    RouteSelection,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import ProviderConfig, Routes, route
from math_tutor.adapters.providers.contracts import (
    ActivityPayload,
    FeedbackPayload,
    Message,
    ModelRequest,
    ProviderError,
    ReadingPayload,
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
    structured_output_mode: Literal["native", "json_prompt"] = "native"
    requires_approval: bool = False


class ProvidersPublic(BaseModel):
    routes: Routes
    providers: list[ProviderPublic]
    policy: ProviderPolicyPublic


class ProbeInput(BaseModel):
    stage: Literal["tutor", "vision"]
    authorize_synthetic_call: bool = False


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
                structured_output_mode=p.capabilities.structured_output_mode,
                requires_approval=p.requires_approval,
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
                private_image_bytes=output.getvalue(),
                response_schema=ReadingPayload.model_json_schema(),
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
        ),
    ]


def probe_error(error: ProviderError) -> ProviderError:
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
    }
    return ProviderError(
        error.code,
        safe_message=details.get(
            error.code,
            "The model test failed. Check the connection and model settings, then retry.",
        ),
    )


@router.post("/providers/{provider_id}/probe", response_model=Acknowledged)
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
    db.commit()
    deadline = time.monotonic() + 90
    for model_request in probe_requests(provider, body.stage):
        db.expire_all()
        if principal(request, db).role != "adult":
            raise HTTPException(403, "Adult access required.")
        if effective_configuration(db).fingerprint() != original_digest:
            raise HTTPException(
                409,
                "Connection or data policy changed during the test. Test the current settings again.",
            )
        db.commit()  # No database lock is held while the model is running.
        remaining = int(deadline - time.monotonic())
        if remaining < 1:
            raise probe_error(ProviderError("timeout"))
        model_request = model_request.model_copy(update={"timeout_seconds": min(45, remaining)})
        try:
            result = complete(provider, model_request)
        except ProviderError as error:
            raise probe_error(error) from None
        payload = result.validated_payload
        if model_request.purpose == "generate" and not isinstance(payload, ActivityPayload):
            raise probe_error(ProviderError("malformed_output"))
        if model_request.purpose == "review" and not isinstance(payload, FeedbackPayload):
            raise probe_error(ProviderError("malformed_output"))
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
