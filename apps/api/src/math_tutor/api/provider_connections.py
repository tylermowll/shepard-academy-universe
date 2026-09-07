"""Adult-only connection setup. Saving never contacts a model endpoint."""

import ipaddress
import os
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from sqlalchemy import delete, func, select

from math_tutor.adapters.db.models import ProviderConnection, ProviderPolicy, ProviderProbe
from math_tutor.adapters.providers.config import ProviderConfig, load_configuration
from math_tutor.adapters.providers.contracts import MAX_CONFIGURED_CONTEXT_LIMIT, Capabilities
from math_tutor.adapters.providers.transports import local_destination
from math_tutor.api.access import Adult, Database
from math_tutor.api.learners import Acknowledged
from math_tutor.provider_secrets import encrypt_key
from math_tutor.providers import effective_configuration

router = APIRouter(prefix="/providers")


class ProviderConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter: Literal["ollama", "vllm", "compatible", "meta"]
    model: str = Field(min_length=1, max_length=2048)
    base_url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True
    boundary: Literal["local_network", "cloud"]
    audience: Literal["adult_only", "mixed"]
    eligibility_record: str = Field(min_length=1, max_length=500)
    image_input: bool = False
    configured_context_limit: int = Field(default=32768, ge=2048, le=MAX_CONFIGURED_CONTEXT_LIMIT)
    structured_output_mode: Literal["native", "json_prompt"] = "native"
    api_key_action: Literal["keep", "replace", "remove"] = "keep"
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192, repr=False)

    @model_validator(mode="after")
    def validate_key_action(self) -> ProviderConnectionInput:
        if (self.api_key_action == "replace") != (self.api_key is not None):
            raise ValueError("Supply a key only when replacing it.")
        if self.api_key is not None:
            value = self.api_key.get_secret_value()
            if not value.strip() or any(ord(char) < 33 or ord(char) > 126 for char in value):
                raise ValueError("API keys must be nonempty printable tokens without spaces.")
        return self


class ProviderConnectionCreate(ProviderConnectionInput):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ProviderPolicyPublic(BaseModel):
    allow_cloud_inference: bool
    app_audience: Literal["adult_only", "mixed"]
    cloud_locked: bool
    audience_locked: bool
    demo_mode: bool


class ProviderPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_cloud_inference: bool
    app_audience: Literal["adult_only", "mixed"]
    acknowledge_data_boundary: bool


def private_setup() -> None:
    if os.getenv("APP_MODE", "private") == "demo":
        raise HTTPException(
            403, "AI connections cannot be changed in the public demo. Start a private app."
        )


def connection_config(body: ProviderConnectionInput) -> ProviderConfig:
    try:
        parsed = urlsplit(body.base_url)
        if any(char.isspace() for char in body.base_url) or "\\" in body.base_url:
            raise ValueError
        path = parsed.path.rstrip("/")
        suffixes = ("/api/chat", "/api") if body.adapter == "ollama" else ("/chat/completions",)
        for suffix in suffixes:
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break
        endpoint = urlunsplit(parsed._replace(path=path))
        # Validate enabled semantics even for a disabled draft: turning it on
        # later must not bypass URL, model, eligibility, or cloud HTTPS checks.
        config = ProviderConfig(
            adapter=body.adapter,
            model=body.model.strip(),
            enabled=True,
            base_url=endpoint,
            data_boundary=body.boundary,
            audience=body.audience,
            eligibility_record=body.eligibility_record.strip(),
            capabilities=Capabilities(
                image_input=body.image_input,
                configured_context_limit=body.configured_context_limit,
                structured_output_mode=body.structured_output_mode,
            ),
        )
        if body.boundary == "local_network":
            try:
                address = ipaddress.ip_address(parsed.hostname or "")
            except ValueError:
                address = None  # DNS is validated and pinned at call time, never on save.
            if address is not None and not local_destination(str(address)):
                raise HTTPException(422, "Use the cloud boundary for a public Internet endpoint.")
        return config.model_copy(update={"enabled": body.enabled})
    except ValueError, ValidationError:
        raise HTTPException(
            422,
            "Check the server URL, exact model name, audience, and eligibility. URLs cannot contain credentials, queries, or fragments; cloud URLs need HTTPS. Meta requires the cloud boundary.",
        ) from None


def save_connection(connection: ProviderConnection, body: ProviderConnectionInput) -> None:
    config = connection_config(body)
    if (
        connection.encrypted_api_key
        and body.api_key_action == "keep"
        and (
            connection.configuration.get("base_url") != config.base_url
            or connection.configuration.get("adapter") != config.adapter
        )
    ):
        raise HTTPException(
            422,
            "A changed server or provider needs a replacement key, or explicitly remove the old key.",
        )
    if body.api_key_action == "replace":
        assert body.api_key is not None
        connection.encrypted_api_key = encrypt_key(connection.id, body.api_key)
        connection.credential_revision = str(uuid4())
    elif body.api_key_action == "remove":
        connection.encrypted_api_key = None
        connection.credential_revision = str(uuid4())
    if body.enabled and body.adapter == "meta" and not connection.encrypted_api_key:
        raise HTTPException(422, "An enabled Meta connection needs an API key.")
    connection.configuration = config.model_copy(update={"requires_approval": True}).model_dump(
        mode="json"
    )


@router.post("/connections", response_model=Acknowledged, status_code=201)
def create_connection(body: ProviderConnectionCreate, db: Database, actor: Adult) -> Acknowledged:
    private_setup()
    if body.id in load_configuration().providers or db.get(ProviderConnection, body.id) is not None:
        raise HTTPException(409, "That connection ID is already in use. Choose another.")
    if (db.scalar(select(func.count()).select_from(ProviderConnection)) or 0) >= 50:
        raise HTTPException(409, "Remove an unused connection before adding another (limit 50).")
    connection = ProviderConnection(
        id=body.id, configuration={}, encrypted_api_key=None, credential_revision=str(uuid4())
    )
    save_connection(connection, body)
    db.add(connection)
    return Acknowledged()


@router.put("/connections/{provider_id}", response_model=Acknowledged)
def update_connection(
    provider_id: str, body: ProviderConnectionInput, db: Database, actor: Adult
) -> Acknowledged:
    private_setup()
    if provider_id in load_configuration().providers:
        raise HTTPException(409, "This connection is managed by the server configuration.")
    connection = db.get(ProviderConnection, provider_id)
    if connection is None:
        raise HTTPException(404, "Connection not found.")
    save_connection(connection, body)
    db.execute(delete(ProviderProbe).where(ProviderProbe.provider_id == provider_id))
    return Acknowledged()


@router.delete("/connections/{provider_id}", response_model=Acknowledged)
def delete_connection(provider_id: str, db: Database, actor: Adult) -> Acknowledged:
    private_setup()
    if provider_id in load_configuration().providers:
        raise HTTPException(409, "This connection is managed by the server configuration.")
    connection = db.get(ProviderConnection, provider_id)
    if connection is None:
        raise HTTPException(404, "Connection not found.")
    routes = effective_configuration(db).routes
    if provider_id in {routes.tutor, routes.vision}:
        raise HTTPException(
            409, "Choose a replacement tutor or photo reader before deleting this connection."
        )
    db.execute(delete(ProviderProbe).where(ProviderProbe.provider_id == provider_id))
    db.delete(connection)
    return Acknowledged()


@router.post("/policy", response_model=Acknowledged)
def update_policy(body: ProviderPolicyInput, db: Database, actor: Adult) -> Acknowledged:
    private_setup()
    if not body.acknowledge_data_boundary:
        raise HTTPException(
            422, "Confirm who will use the app and whether work may leave your network."
        )
    config = effective_configuration(db)
    if (
        "ALLOW_CLOUD_INFERENCE" in os.environ
        and body.allow_cloud_inference != config.allow_cloud_inference
    ) or ("APP_AUDIENCE" in os.environ and body.app_audience != config.app_audience):
        raise HTTPException(
            409, "This policy is locked by the server environment. Ask the operator to update it."
        )
    row = db.get(ProviderPolicy, "active")
    if row is None:
        db.add(
            ProviderPolicy(
                name="active",
                allow_cloud_inference=body.allow_cloud_inference,
                app_audience=body.app_audience,
            )
        )
    else:
        row.allow_cloud_inference = body.allow_cloud_inference
        row.app_audience = body.app_audience
    return Acknowledged()
