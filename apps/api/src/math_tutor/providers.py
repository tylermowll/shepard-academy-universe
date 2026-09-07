"""Policy, probes and bounded provider selection shared by API and worker."""

import hashlib
import os
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import (
    Learner,
    ProviderConnection,
    ProviderPolicy,
    ProviderProbe,
    RouteSelection,
)
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.config import (
    Configuration,
    ProviderConfig,
    Routes,
    load_configuration,
    route,
)
from math_tutor.adapters.providers.contracts import ModelRequest, ModelResult, ProviderError
from math_tutor.adapters.providers.execution import complete_bounded
from math_tutor.adapters.providers.transports import MockProvider
from math_tutor.provider_secrets import decrypt_key


def effective_configuration(db: Session) -> Configuration:
    configuration = load_configuration()
    providers = dict(configuration.providers)
    for connection in db.scalars(select(ProviderConnection)):
        if connection.id in providers:
            # Never shadow a newly introduced operator-file route with a saved
            # connection (or accidentally use that saved route's credential).
            raise ProviderError(
                "configuration_conflict",
                safe_message="A saved connection ID conflicts with the server configuration. Rename the server entry.",
            )
        secret = (
            decrypt_key(connection.id, connection.encrypted_api_key)
            if connection.encrypted_api_key
            else None
        )
        providers[connection.id] = ProviderConfig.model_validate(
            connection.configuration
        ).model_copy(
            update={
                "api_key_secret": secret,
                "credential_unavailable": bool(connection.encrypted_api_key and secret is None),
                "credential_revision": connection.credential_revision,
            }
        )
    policy = db.get(ProviderPolicy, "active")
    cloud_setting = os.getenv("ALLOW_CLOUD_INFERENCE")
    audience_setting = os.getenv("APP_AUDIENCE")
    configuration = configuration.model_copy(
        update={
            "providers": providers,
            "allow_cloud_inference": cloud_setting == "true"
            if cloud_setting is not None
            else bool(policy and policy.allow_cloud_inference),
            "app_audience": ("adult_only" if audience_setting == "adult_only" else "mixed")
            if audience_setting is not None
            else (policy.app_audience if policy else "mixed"),
        }
    )
    selection = db.get(RouteSelection, "active")
    if selection:
        configuration = configuration.model_copy(
            update={"routes": Routes.model_validate(selection.routes)}
        )
    return configuration


def probe_fingerprint(provider: ProviderConfig, stage: str) -> str:
    # Capability evidence is retained while an adult separately approves the
    # tested connection for learner data. Credentials retain their random revision.
    return hashlib.sha256(
        (
            provider.model_dump_json(exclude={"requires_approval"}) + stage + ":ai-tutor-probe-v2"
        ).encode()
    ).hexdigest()


def probe_is_current(db: Session, provider: ProviderConfig, stage: str) -> bool:
    if provider.credential_unavailable:
        return False
    if provider.adapter == "mock":
        return True
    probe = db.get(ProviderProbe, probe_fingerprint(provider, stage))
    return probe is not None and probe.tested_at >= utcnow() - timedelta(days=7)


def authorize_route(
    db: Session, config: Configuration, stage: Literal["tutor", "vision"], learner_id: UUID
) -> tuple[str, ProviderConfig]:
    learner = db.get(Learner, learner_id)
    if learner is None or not learner.enabled or learner.deleted_at is not None:
        raise ProviderError("access_revoked")
    name, provider = route(config, stage, learner.eligibility)
    if not probe_is_current(db, provider, stage):
        raise ProviderError(
            "probe_required",
            safe_message="An adult must run a synthetic capability probe for this route.",
        )
    return name, provider


def complete(provider: ProviderConfig, request: ModelRequest) -> ModelResult:
    if provider.adapter == "mock":
        return MockProvider().complete(request)
    return complete_bounded(provider, request)
