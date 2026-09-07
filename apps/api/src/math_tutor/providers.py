"""Policy, probes and bounded provider selection shared by API and worker."""

import hashlib
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import Learner, ProviderProbe, RouteSelection
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import (
    Configuration,
    ProviderConfig,
    Routes,
    load_configuration,
    route,
)
from math_tutor.adapters.providers.contracts import ModelRequest, ModelResult, ProviderError
from math_tutor.adapters.providers.transports import BedrockProvider, HTTPProvider, MockProvider


def effective_configuration(db: Session) -> Configuration:
    configuration = load_configuration()
    selection = db.get(RouteSelection, "active")
    if selection:
        configuration = configuration.model_copy(
            update={"routes": Routes.model_validate(selection.routes)}
        )
    return configuration


def probe_fingerprint(provider: ProviderConfig, stage: str) -> str:
    return hashlib.sha256((provider.model_dump_json() + stage).encode()).hexdigest()


def authorize_route(
    db: Session, config: Configuration, stage: Literal["tutor", "vision"], learner_id: UUID
) -> tuple[str, ProviderConfig]:
    learner = db.get(Learner, learner_id)
    if learner is None or not learner.enabled or learner.deleted_at is not None:
        raise ProviderError("access_revoked")
    name, provider = route(config, stage, learner.eligibility)
    if provider.adapter != "mock":
        probe = db.get(ProviderProbe, probe_fingerprint(provider, stage))
        if probe is None or probe.tested_at < utcnow() - timedelta(days=7):
            raise ProviderError(
                "probe_required",
                safe_message="An adult must run a synthetic capability probe for this route.",
            )
    return name, provider


def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
    if provider.adapter == "mock":
        return MockProvider().complete(request)
    if provider.adapter == "bedrock":
        return BedrockProvider(provider).complete(request)
    return HTTPProvider(provider).complete(request)
