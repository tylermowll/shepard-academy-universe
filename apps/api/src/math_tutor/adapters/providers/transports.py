"""Explicit wire mappings. Network clients never follow redirects or retry implicitly."""

from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import json
import os
import socket
import time
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

import boto3
import httpx2 as httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from math_tutor.adapters.images import NORMALIZED_IMAGE_MIME_TYPE
from math_tutor.adapters.providers.config import ProviderConfig, blocked_destination
from math_tutor.adapters.providers.contracts import (
    ActivityPayload,
    FeedbackPayload,
    InterpretationPayload,
    ModelRequest,
    ModelResult,
    ProviderError,
    ReadingPayload,
    TutorPayload,
)


class WireObject(BaseModel):
    """Validate consumed fields without rejecting vendor-specific metadata."""

    model_config = ConfigDict(strict=True, extra="ignore")


class ChatMessage(WireObject):
    content: str | None = None
    refusal: str | None = None


class ChatChoice(WireObject):
    message: ChatMessage
    finish_reason: str | None = None


class CompletionTokenDetails(WireObject):
    reasoning_tokens: int = Field(default=0, ge=0)


class ChatUsage(WireObject):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    completion_tokens_details: CompletionTokenDetails | None = None


class ChatResponse(WireObject):
    choices: list[ChatChoice] = Field(min_length=1)
    usage: ChatUsage = Field(default_factory=ChatUsage)


class OllamaResponse(WireObject):
    done: bool
    done_reason: str | None = None
    message: ChatMessage
    prompt_eval_count: int = Field(default=0, ge=0)
    eval_count: int = Field(default=0, ge=0)


class BedrockBlock(WireObject):
    text: str | None = None


class BedrockMessage(WireObject):
    content: list[BedrockBlock]


class BedrockOutput(WireObject):
    message: BedrockMessage


class BedrockMetrics(WireObject):
    latencyMs: int = Field(default=0, ge=0)


class BedrockUsage(WireObject):
    inputTokens: int = Field(default=0, ge=0)
    outputTokens: int = Field(default=0, ge=0)
    totalTokens: int = Field(default=0, ge=0)
    cacheReadInputTokens: int = Field(default=0, ge=0)
    cacheWriteInputTokens: int = Field(default=0, ge=0)


class BedrockResponse(WireObject):
    stopReason: str
    output: BedrockOutput | None = None
    usage: BedrockUsage = Field(default_factory=BedrockUsage)
    metrics: BedrockMetrics = Field(default_factory=BedrockMetrics)


def strict_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Produce the closed, fully-required schema expected by strict decoders.

    Pydantic represents a nullable field with a Python default as optional in
    JSON Schema. OpenAI-style strict structured-output APIs instead require
    every declared property and express optional values with ``null``. They may
    also reject the ``default`` annotation. Keep local validation permissive,
    but normalize the provider wire copy recursively.
    """
    normalized = copy.deepcopy(schema)

    def close(value: object) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for child in value.values():
                close(child)
        elif isinstance(value, list):
            for child in value:
                close(child)

    close(normalized)
    return normalized


def pinned_endpoints(url: httpx.URL, *, local_only: bool = False) -> list[httpx.URL]:
    """Resolve once and pin allowed addresses, preserving Host and TLS SNI separately."""
    try:
        addresses = socket.getaddrinfo(
            url.host, url.port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except OSError:
        raise ProviderError("unavailable", True) from None
    if not addresses or any(blocked_destination(str(row[4][0])) for row in addresses):
        raise ProviderError("invalid_endpoint")
    if local_only and any(not local_destination(str(row[4][0])) for row in addresses):
        raise ProviderError(
            "invalid_endpoint",
            safe_message="A local connection must resolve to a private network address. Use the cloud boundary for a hosted provider.",
        )
    return [url.copy_with(host=host) for host in dict.fromkeys(str(row[4][0]) for row in addresses)]


def local_destination(host: str) -> bool:
    address = ipaddress.ip_address(host)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return (
        address.is_private
        or address.is_loopback
        or address in ipaddress.ip_network("100.64.0.0/10")
    )


def validate_payload(
    request: ModelRequest, text: str
) -> TutorPayload | InterpretationPayload | ActivityPayload | ReadingPayload | FeedbackPayload:
    if len(text) > 16000:
        raise ProviderError("malformed_output")
    try:
        if request.purpose == "generate":
            return ActivityPayload.model_validate_json(text)
        if request.purpose == "read":
            return ReadingPayload.model_validate_json(text)
        if request.purpose == "review":
            return FeedbackPayload.model_validate_json(text)
        if request.stage == "vision":
            return InterpretationPayload.model_validate_json(text)
        return TutorPayload.model_validate_json(text)
    except ValidationError:
        raise ProviderError(
            "malformed_output",
            safe_message="Provider output did not match the required format. Your work is saved.",
        ) from None


def check_request(config: ProviderConfig, request: ModelRequest) -> None:
    if request.model_id != config.model or not config.enabled:
        raise ProviderError("configuration_mismatch")
    if not config.capabilities.text_input:
        raise ProviderError("unsupported_modality")
    if request.private_image_bytes is not None and (
        not config.capabilities.image_input
        or config.capabilities.max_images < 1
        or NORMALIZED_IMAGE_MIME_TYPE not in config.capabilities.accepted_image_mime_types
    ):
        raise ProviderError("unsupported_modality")
    # UTF-8 bytes are a conservative token upper bound, including schema overhead.
    size = len(
        (
            request.system_instruction
            + json.dumps(request.response_schema)
            + "".join(m.content for m in request.ordered_messages)
        ).encode()
    )
    image_budget = 4096 if request.private_image_bytes else 0
    if (
        size + image_budget + request.max_output_tokens
        > config.capabilities.configured_context_limit
    ):
        raise ProviderError("context_limit")


class MockProvider:
    def complete(self, request: ModelRequest) -> ModelResult:
        payload: (
            TutorPayload
            | InterpretationPayload
            | ActivityPayload
            | ReadingPayload
            | FeedbackPayload
        )
        if request.purpose == "generate":
            payload = ActivityPayload(
                problem_text="Synthetic practice: Two groups each observe a seedling for a week. One receives light and one stays in shade. Describe one observation you would record and explain how it could support a comparison.",
                concept_focus="Synthetic example: observations and evidence",
            )
        elif request.purpose == "read":
            # Exact encodings of the original public '2/5' fixture: direct
            # upload and preview-then-upload. JPEG normalization is lossy, so
            # those two supported paths have distinct byte hashes. Never
            # pretend the mock can recognize arbitrary learner handwriting.
            known = hashlib.sha256(request.private_image_bytes or b"").hexdigest() in {
                "7420130d9e680522a2ffd0a3b014794e9e9bbcaf3a2a5609359c33d31936767d",
                "b8e617a2dc35adc3549d36602080f29c0bae9200d706d075f62da73a5efddc1b",
            }
            payload = ReadingPayload(
                transcription="2/5" if known else "",
                quality="clear" if known else "unreadable",
                confidence=1.0 if known else 0.0,
                ambiguities=[] if known else ["Mock provider cannot read this photograph."],
                organization_feedback=[
                    "Synthetic fixture reading only. For real work, show the question number, leave space between steps, and keep the full page in focus."
                ],
                rejection_reason=None
                if known
                else "No handwriting model is configured. Choose an image-capable provider; use clear, well-lit, organized work.",
            )
        elif request.purpose == "review":
            payload = FeedbackPayload(
                strengths=["Synthetic feedback: you submitted work for discussion."],
                guidance=[
                    "Connect one specific observation to the claim it supports. Explain why that observation matters instead of giving only a conclusion."
                ],
                next_step="Revise one sentence to connect your evidence and explanation.",
                concepts=["Evidence and explanation"],
                uncertainty_note="Synthetic mock response, not an assessment of your work.",
            )
        elif request.stage == "vision":
            payload = InterpretationPayload(
                transcription="",
                ambiguities=[
                    "The mock provider does not read handwriting. Type the transcription to exercise confirmation."
                ],
            )
        else:
            payload = TutorPayload(
                message_kind="question_response",
                message_markdown="Synthetic tutor response: use equal-sized parts when comparing fractions.",
                suggested_next_action="revise_answer",
            )
        return ModelResult(validated_payload=payload, model_id=request.model_id)


class HTTPProvider:
    def __init__(self, config: ProviderConfig, client: httpx.Client | None = None):
        self.config = config
        self.client = client

    def wire(self, request: ModelRequest) -> tuple[str, dict[str, Any]]:
        config = self.config
        system = request.system_instruction
        if config.capabilities.structured_output_mode == "json_prompt":
            system += " Return only JSON matching: " + json.dumps(request.response_schema)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(m.model_dump() for m in request.ordered_messages)
        if not request.ordered_messages or request.ordered_messages[-1].role != "user":
            raise ProviderError("invalid_request")
        if request.private_image_bytes:
            encoded = base64.b64encode(request.private_image_bytes).decode("ascii")
            if config.adapter == "ollama":
                messages[-1]["images"] = [encoded]
            else:
                messages[-1]["content"] = [
                    {"type": "text", "text": messages[-1]["content"]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{NORMALIZED_IMAGE_MIME_TYPE};base64," + encoded
                        },
                    },
                ]
        body: dict[str, Any] = {"model": request.model_id, "messages": messages, "stream": False}
        if config.adapter == "ollama":
            body["options"] = {"num_predict": request.max_output_tokens}
            body["format"] = (
                request.response_schema
                if config.capabilities.structured_output_mode == "native"
                else "json"
            )
            return "/api/chat", body
        body["max_tokens"] = request.max_output_tokens
        if config.adapter == "meta" and config.capabilities.reasoning_effort != "default":
            body["reasoning_effort"] = config.capabilities.reasoning_effort
        if config.capabilities.structured_output_mode == "native":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "tutor_response",
                    "strict": True,
                    "schema": strict_response_schema(request.response_schema),
                },
            }
        return "/chat/completions", body

    def complete(self, request: ModelRequest) -> ModelResult:
        check_request(self.config, request)
        path, body = self.wire(request)
        if self.config.credential_unavailable:
            raise ProviderError(
                "authentication",
                safe_message="The saved API key cannot be unlocked. An adult must replace it in Settings.",
            )
        key = (
            self.config.api_key_secret.get_secret_value()
            if self.config.api_key_secret is not None
            else (os.getenv(self.config.api_key_env, "") if self.config.api_key_env else "")
        )
        if self.config.api_key_env and not key:
            raise ProviderError("authentication")
        headers = {"Authorization": "Bearer " + key} if key else {}
        start = time.monotonic()
        client = self.client or httpx.Client(
            timeout=request.timeout_seconds, follow_redirects=False, trust_env=False
        )
        try:
            endpoint = httpx.URL((self.config.base_url or "").rstrip("/") + path)
            targets = (
                [endpoint]
                if self.client is not None
                else pinned_endpoints(
                    endpoint, local_only=self.config.data_boundary == "local_network"
                )
            )
            headers["Host"] = endpoint.netloc.decode("ascii")
            with ExitStack() as stack:
                response = None
                for target in targets:
                    try:
                        response = stack.enter_context(
                            client.stream(
                                "POST",
                                target,
                                json=body,
                                headers=headers,
                                timeout=request.timeout_seconds,
                                extensions={"sni_hostname": endpoint.host},
                            )
                        )
                        break
                    except httpx.ConnectError, httpx.ConnectTimeout:
                        # Only try another resolved address before HTTP transmission.
                        if target == targets[-1]:
                            raise
                assert response is not None
                if response.status_code != 200:
                    code = {
                        401: "authentication",
                        403: "authentication",
                        429: "throttled",
                        413: "context_limit",
                        400: "invalid_request",
                    }.get(response.status_code, "unavailable")
                    retry_after = response.headers.get("retry-after", "1")
                    delay = min(300, max(1, int(retry_after))) if retry_after.isdigit() else 1
                    raise ProviderError(
                        code,
                        response.status_code == 429 or response.status_code >= 500,
                        delay,
                        http_status=response.status_code,
                    )
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 262144:
                        raise ProviderError("malformed_output")
            usage: dict[str, int] = {}
            if self.config.adapter == "ollama":
                ollama = OllamaResponse.model_validate_json(chunks)
                if ollama.done_reason == "length":
                    raise ProviderError("output_limit", completion_reason="length")
                if not ollama.done or ollama.done_reason not in {"stop", None}:
                    raise ProviderError("incomplete_output", completion_reason=ollama.done_reason)
                content = ollama.message.content
                usage = ollama.model_dump(
                    include={"prompt_eval_count", "eval_count"}, exclude_unset=True
                )
            else:
                chat = ChatResponse.model_validate_json(chunks)
                choice = chat.choices[0]
                if choice.message.refusal or choice.finish_reason == "content_filter":
                    raise ProviderError(
                        "refusal",
                        safe_message="The provider declined this request. Try built-in help.",
                    )
                if choice.finish_reason == "length":
                    raise ProviderError("output_limit", completion_reason="length")
                if choice.finish_reason != "stop":
                    raise ProviderError(
                        "incomplete_output", completion_reason=choice.finish_reason or "missing"
                    )
                content = choice.message.content
                usage = chat.usage.model_dump(
                    exclude_unset=True, exclude={"completion_tokens_details"}
                )
                if (
                    chat.usage.completion_tokens_details is not None
                    and "reasoning_tokens" in chat.usage.completion_tokens_details.model_fields_set
                ):
                    usage["reasoning_tokens"] = (
                        chat.usage.completion_tokens_details.reasoning_tokens
                    )
            if not isinstance(content, str):
                raise ProviderError("malformed_output")
            return ModelResult(
                validated_payload=validate_payload(request, content),
                model_id=request.model_id,
                reported_usage=usage,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except httpx.TimeoutException:
            raise ProviderError("timeout", True) from None
        except httpx.RequestError:
            raise ProviderError("unavailable", True) from None
        except ValueError, KeyError, IndexError, TypeError:
            raise ProviderError("malformed_output") from None
        finally:
            if self.client is None:
                client.close()


class BedrockProvider:
    def __init__(self, config: ProviderConfig, client: BedrockRuntimeClient | None = None):
        self.config = config
        self.client = client

    def wire(self, request: ModelRequest) -> dict[str, Any]:
        system = request.system_instruction
        if self.config.capabilities.structured_output_mode == "json_prompt":
            system += " Return only JSON matching: " + json.dumps(request.response_schema)
        messages = [
            {"role": m.role, "content": [{"text": m.content}]} for m in request.ordered_messages
        ]
        body: dict[str, Any] = {
            "modelId": request.model_id,
            "system": [{"text": system}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": request.max_output_tokens},
        }
        if request.private_image_bytes:
            body["messages"][-1]["content"].append(
                {"image": {"format": "jpeg", "source": {"bytes": request.private_image_bytes}}}
            )
        if self.config.capabilities.structured_output_mode == "native":
            body["outputConfig"] = {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": json.dumps(request.response_schema),
                            "name": "tutor_response",
                        }
                    },
                }
            }
        return body

    def complete(self, request: ModelRequest) -> ModelResult:
        check_request(self.config, request)
        client = self.client
        try:
            if client is None:
                client = boto3.client(
                    "bedrock-runtime",
                    region_name=self.config.region,
                    config=Config(
                        retries={"total_max_attempts": 1},
                        connect_timeout=5,
                        read_timeout=request.timeout_seconds,
                    ),
                )
            raw = client.converse(**self.wire(request))
            data = BedrockResponse.model_validate(raw)
            reason = data.stopReason
            if reason in {"guardrail_intervened", "content_filtered"}:
                raise ProviderError("refusal")
            if reason == "max_tokens":
                raise ProviderError("output_limit", completion_reason="max_tokens")
            if reason != "end_turn":
                raise ProviderError("incomplete_output", completion_reason=reason)
            if data.output is None:
                raise ProviderError("malformed_output")
            content = "".join(block.text or "" for block in data.output.message.content)
            return ModelResult(
                validated_payload=validate_payload(request, content),
                model_id=request.model_id,
                reported_usage=data.usage.model_dump(exclude_unset=True),
                latency_ms=data.metrics.latencyMs,
                finish_reason="end_turn",
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            retryable = code in {
                "ThrottlingException",
                "ServiceUnavailableException",
                "ModelTimeoutException",
                "InternalServerException",
            }
            raise ProviderError(
                "throttled" if code == "ThrottlingException" else "provider_error", retryable
            ) from None
        except BotoCoreError:
            raise ProviderError("unavailable", True) from None
        except KeyError, TypeError, ValueError:
            raise ProviderError("malformed_output") from None
        finally:
            if self.client is None and client is not None:
                client.close()
