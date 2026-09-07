"""Validated operator configuration and fail-closed policy routing."""

import hashlib
import ipaddress
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from math_tutor.adapters.providers.contracts import Capabilities, ProviderError


def blocked_destination(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in {"metadata", "metadata.google.internal", "instance-data.ec2.internal"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id is not None:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return (
        address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or str(address) == "fd00:ec2::254"
    )


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    adapter: Literal["mock", "meta", "ollama", "vllm", "compatible", "bedrock"]
    model: str = Field(min_length=1, max_length=2048)
    enabled: bool = False
    base_url: str | None = None
    api_key_env: str | None = None
    region: str | None = None
    data_boundary: Literal["synthetic", "local_network", "cloud"] = "local_network"
    audience: Literal["adult_only", "mixed"] = "adult_only"
    eligibility_record: str = Field(default="", max_length=500)
    capabilities: Capabilities = Field(default_factory=Capabilities)

    @model_validator(mode="after")
    def validate_route(self) -> ProviderConfig:
        if not self.enabled:
            return self
        if "REPLACE" in self.model or self.model == "latest":
            raise ValueError("Enabled models need an exact operator-selected identifier.")
        if self.adapter == "mock":
            if self.data_boundary != "synthetic":
                raise ValueError("Mock boundary must be synthetic.")
            return self
        if self.data_boundary == "synthetic":
            raise ValueError("Only mock can use the synthetic boundary.")
        if not self.eligibility_record:
            raise ValueError("Live routes need an operator eligibility record.")
        if self.adapter == "meta" and (
            self.data_boundary != "cloud" or self.audience != "adult_only"
        ):
            raise ValueError("Meta requires the adult-only cloud policy.")
        if self.adapter == "bedrock":
            if not self.region or self.data_boundary != "cloud":
                raise ValueError("Bedrock requires an explicit region and cloud boundary.")
        else:
            url = urlsplit(self.base_url or "")
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or blocked_destination(url.hostname or "")
            ):
                raise ValueError("Invalid provider endpoint.")
            if url.port is not None and not 1 <= url.port <= 65535:
                raise ValueError("Invalid provider port.")
            if self.data_boundary == "cloud" and url.scheme != "https":
                raise ValueError("Cloud endpoints require HTTPS.")
        return self


class Routes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tutor: str = "demo"
    vision: str = "demo"


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    routes: Routes = Field(default_factory=Routes)
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "demo": ProviderConfig(
                adapter="mock",
                model="fixture-v1",
                enabled=True,
                data_boundary="synthetic",
                audience="mixed",
                capabilities=Capabilities(image_input=True),
            )
        }
    )

    def fingerprint(self) -> str:
        policy = (
            self.model_dump_json()
            + os.getenv("APP_AUDIENCE", "mixed")
            + os.getenv("ALLOW_CLOUD_INFERENCE", "false")
            + os.getenv("APP_MODE", "private")
        )
        return hashlib.sha256(policy.encode()).hexdigest()


def load_configuration() -> Configuration:
    name = os.getenv("PROVIDER_CONFIG")
    if name is None:
        return Configuration()
    path = Path(name)
    if path.stat().st_size > 65536:
        raise ValueError("Provider configuration is too large.")
    try:
        return Configuration.model_validate(yaml.safe_load(path.read_text()))
    except ValueError, yaml.YAMLError:
        raise ValueError(
            "Provider configuration does not match the public example schema."
        ) from None


def route(
    configuration: Configuration, stage: Literal["tutor", "vision"], eligibility: str
) -> tuple[str, ProviderConfig]:
    name = getattr(configuration.routes, stage)
    provider = configuration.providers.get(name)
    if provider is None or not provider.enabled:
        raise ProviderError(
            "route_disabled",
            safe_message="The configured route is disabled. Ask an adult to configure it.",
        )
    if provider.adapter != "mock":
        if os.getenv("APP_MODE", "private") == "demo":
            raise ProviderError("demo_policy")
        if (
            provider.data_boundary == "cloud"
            and os.getenv("ALLOW_CLOUD_INFERENCE", "false") != "true"
        ):
            raise ProviderError("cloud_disabled")
        if provider.audience == "adult_only" and (
            eligibility != "adult" or os.getenv("APP_AUDIENCE", "mixed") != "adult_only"
        ):
            raise ProviderError(
                "audience_blocked",
                safe_message="This route is not eligible for the configured audience.",
            )
        if provider.adapter == "meta" and eligibility != "adult":
            raise ProviderError("audience_blocked")
    if not provider.capabilities.text_input:
        raise ProviderError("unsupported_modality")
    if stage == "vision" and not provider.capabilities.image_input:
        raise ProviderError(
            "unsupported_modality",
            safe_message="The selected route does not support photographs. Use typed input.",
        )
    return name, provider
