"""Adult-only redacted provider setup and explicitly requested synthetic probes."""

from io import BytesIO
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from PIL import Image, ImageDraw
from pydantic import BaseModel
from sqlalchemy import select

from math_tutor.adapters.db.models import ModelCall, ProviderProbe, RouteSelection
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import Routes, route
from math_tutor.adapters.providers.contracts import (
    InterpretationPayload,
    Message,
    ModelRequest,
    TutorPayload,
)
from math_tutor.api.access import Adult, Database, principal
from math_tutor.api.learners import Acknowledged
from math_tutor.providers import complete, effective_configuration, probe_fingerprint

router = APIRouter(prefix="/api/v1/admin", tags=["provider administration"])


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


class ProvidersPublic(BaseModel):
    routes: Routes
    providers: list[ProviderPublic]


class ProbeInput(BaseModel):
    stage: Literal["tutor", "vision"]
    authorize_synthetic_call: bool = False


class SelectRoutes(Routes):
    acknowledge_data_boundary: bool


@router.get("/providers", response_model=ProvidersPublic)
def providers(db: Database, actor: Adult) -> ProvidersPublic:
    config = effective_configuration(db)
    return ProvidersPublic(
        routes=config.routes,
        providers=[
            ProviderPublic(
                id=name,
                adapter=p.adapter,
                model=p.model,
                enabled=p.enabled,
                boundary=p.data_boundary,
                audience=p.audience,
                image_input=p.capabilities.image_input,
                tutor_probed=p.adapter == "mock"
                or db.get(ProviderProbe, probe_fingerprint(p, "tutor")) is not None,
                vision_probed=p.adapter == "mock"
                or db.get(ProviderProbe, probe_fingerprint(p, "vision")) is not None,
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
        route(updated, stage, "adult")
    row = db.get(RouteSelection, "active")
    if row is None:
        db.add(RouteSelection(name="active", routes=routes.model_dump()))
    else:
        row.routes = routes.model_dump()
    return Acknowledged()


@router.post("/providers/{provider_id}/probe", response_model=Acknowledged)
def probe(
    provider_id: str, body: ProbeInput, request: Request, db: Database, actor: Adult
) -> Acknowledged:
    config = effective_configuration(db)
    config = config.model_copy(update={"routes": Routes(tutor=provider_id, vision=provider_id)})
    name, provider = route(config, body.stage, "adult")
    if provider.adapter != "mock" and not body.authorize_synthetic_call:
        raise HTTPException(422, "Explicit synthetic-call authorization is required.")
    image_bytes = None
    if body.stage == "vision":
        image = Image.new("RGB", (256, 128), "white")
        ImageDraw.Draw(image).text((30, 40), "1/2", fill="black", font_size=40)
        output = BytesIO()
        image.save(output, "PNG")
        image_bytes = output.getvalue()
    model_request = ModelRequest(
        operation_id=uuid4(),
        stage=body.stage,
        model_id=provider.model,
        system_instruction="Return the required JSON. For vision, transcribe only the visible fraction. For text, give one general hint about adding fractions.",
        ordered_messages=[
            Message(
                role="user",
                content="Read this fraction."
                if image_bytes
                else "How do common denominators help?",
            )
        ],
        private_image_bytes=image_bytes,
        response_schema=(
            InterpretationPayload if image_bytes else TutorPayload
        ).model_json_schema(),
    )
    db.commit()
    result = complete(provider, model_request)
    if (
        body.stage == "vision"
        and provider.adapter != "mock"
        and (
            not isinstance(result.validated_payload, InterpretationPayload)
            or result.validated_payload.transcription.strip() != "1/2"
        )
    ):
        raise HTTPException(422, "Synthetic vision probe did not read the known fraction.")
    db.connection(execution_options={"sqlite_begin_immediate": True})
    current = principal(request, db)
    if current.role != "adult":
        raise HTTPException(403, "Adult access required.")
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
