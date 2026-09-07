"""Explicit wire mappings. Network clients never follow redirects or retry implicitly."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import TYPE_CHECKING, Any, cast

import boto3
import httpx2 as httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
from pydantic import ValidationError

from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import (
    InterpretationPayload,
    ModelRequest,
    ModelResult,
    ProviderError,
    TutorPayload,
)


def validate_payload(request: ModelRequest, text: str) -> TutorPayload | InterpretationPayload:
    if len(text) > 16000:
        raise ProviderError("malformed_output")
    try:
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
        or "image/png" not in config.capabilities.accepted_image_mime_types
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
        payload: TutorPayload | InterpretationPayload
        if request.stage == "vision":
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
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
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
        if config.capabilities.structured_output_mode == "native":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "tutor_response",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        return "/chat/completions", body

    def complete(self, request: ModelRequest) -> ModelResult:
        check_request(self.config, request)
        path, body = self.wire(request)
        key = os.getenv(self.config.api_key_env, "") if self.config.api_key_env else ""
        if self.config.api_key_env and not key:
            raise ProviderError("authentication")
        headers = {"Authorization": "Bearer " + key} if key else {}
        start = time.monotonic()
        client = self.client or httpx.Client(
            timeout=request.timeout_seconds, follow_redirects=False, trust_env=False
        )
        try:
            with client.stream(
                "POST",
                (self.config.base_url or "").rstrip("/") + path,
                json=body,
                headers=headers,
                timeout=request.timeout_seconds,
            ) as response:
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
                        code, response.status_code == 429 or response.status_code >= 500, delay
                    )
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 262144:
                        raise ProviderError("malformed_output")
                data = json.loads(chunks)
            usage: dict[str, int] = {}
            if self.config.adapter == "ollama":
                if data.get("done") is not True or data.get("done_reason") not in {"stop", None}:
                    raise ProviderError("incomplete_output")
                content = data["message"]["content"]
                for key_name in ("prompt_eval_count", "eval_count"):
                    value = data.get(key_name)
                    if isinstance(value, int) and value >= 0:
                        usage[key_name] = value
            else:
                choice = data["choices"][0]
                if (
                    choice["message"].get("refusal")
                    or choice.get("finish_reason") == "content_filter"
                ):
                    raise ProviderError(
                        "refusal",
                        safe_message="The provider declined this request. Try built-in help.",
                    )
                if choice.get("finish_reason") != "stop":
                    raise ProviderError("incomplete_output")
                content = choice["message"]["content"]
                for key_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = data.get("usage", {}).get(key_name)
                    if isinstance(value, int) and value >= 0:
                        usage[key_name] = value
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
                {"image": {"format": "png", "source": {"bytes": request.private_image_bytes}}}
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
        client = self.client or boto3.client(
            "bedrock-runtime",
            region_name=self.config.region,
            config=Config(
                retries={"total_max_attempts": 1},
                connect_timeout=5,
                read_timeout=request.timeout_seconds,
            ),
        )
        try:
            raw = client.converse(**self.wire(request))
            data = cast(dict[str, Any], raw)
            reason = data.get("stopReason")
            if reason in {"guardrail_intervened", "content_filtered"}:
                raise ProviderError("refusal")
            if reason != "end_turn":
                raise ProviderError("incomplete_output")
            content = "".join(
                block["text"] for block in data["output"]["message"]["content"] if "text" in block
            )
            return ModelResult(
                validated_payload=validate_payload(request, content),
                model_id=request.model_id,
                reported_usage={
                    k: v for k, v in data.get("usage", {}).items() if isinstance(v, int) and v >= 0
                },
                latency_ms=data.get("metrics", {}).get("latencyMs", 0),
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
            if self.client is None:
                client.close()
