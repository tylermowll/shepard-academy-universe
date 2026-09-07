"""Provider-neutral, bounded requests; no model-controlled permissions or verdicts."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text_input: bool = True
    image_input: bool = False
    structured_output_mode: Literal["native", "json_prompt"] = "native"
    max_images: int = Field(default=1, ge=0, le=1)
    accepted_image_mime_types: list[str] = Field(default_factory=lambda: ["image/png"])
    configured_context_limit: int = Field(default=8192, ge=2048, le=131072)


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)


class TutorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1"] = "1"
    message_kind: Literal["hint", "explanation", "worked_example", "solution", "question_response"]
    message_markdown: str = Field(min_length=1, max_length=6000)
    suggested_next_action: Literal["revise_answer", "ask_question", "continue"]
    uncertainty_note: str | None = Field(default=None, max_length=500)


class InterpretationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    transcription: str = Field(max_length=4000)
    final_answer: str | None = Field(default=None, max_length=128)
    ambiguities: list[str] = Field(max_length=20)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    stage: Literal["tutor", "vision"]
    model_id: str
    system_instruction: str = Field(max_length=6000)
    ordered_messages: list[Message] = Field(max_length=12)
    private_image_bytes: bytes | None = Field(default=None, exclude=True)
    response_schema: dict[str, Any]
    max_output_tokens: int = Field(default=1200, ge=64, le=4096)
    timeout_seconds: int = Field(default=90, ge=1, le=90)


class ModelResult(BaseModel):
    validated_payload: TutorPayload | InterpretationPayload
    provider_request_id: str | None = None
    model_id: str
    reported_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = 0
    finish_reason: str = "stop"


@dataclass
class ProviderError(Exception):
    code: str
    retryable: bool = False
    retry_after_seconds: int = 1
    safe_message: str = "Provider could not complete this operation. Your work is saved."
    provider_request_id: str | None = None


class Provider(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...
