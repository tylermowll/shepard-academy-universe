"""Task-shaped payloads cannot introduce grading/state fields or invent vision."""

import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from math_tutor.adapters.images import normalize
from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import (
    ActivityPayload,
    Capabilities,
    FeedbackPayload,
    Message,
    ModelRequest,
    ProviderError,
    ReadingPayload,
)
from math_tutor.adapters.providers.transports import (
    HTTPProvider,
    MockProvider,
    check_request,
    strict_response_schema,
    validate_payload,
)
from math_tutor.tutoring import bounded_messages, can_read, copied_reference


def reading(**changes: object) -> ReadingPayload:
    return ReadingPayload.model_validate(
        {
            "transcription": "One observation.\nOne explanation.",
            "quality": "clear",
            "confidence": 0.95,
            "ambiguities": [],
            "organization_feedback": ["Keep observations and explanations on separate lines."],
            "rejection_reason": None,
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"quality": "uncertain"},
        {"quality": "unreadable"},
        {"confidence": 0.84},
        {"ambiguities": ["The order is unclear"]},
        {"transcription": " "},
        {"rejection_reason": "The last line is missing"},
    ],
)
def test_reading_threshold_is_fail_closed(changes: dict[str, object]) -> None:
    assert not can_read(reading(**changes))
    assert can_read(reading())


def test_reading_quality_confidence_required_and_no_verdict_fields() -> None:
    for missing in ["quality", "confidence", "ambiguities"]:
        data = reading().model_dump()
        del data[missing]
        with pytest.raises(ValidationError):
            ReadingPayload.model_validate(data)
    with pytest.raises(ValidationError):
        ActivityPayload.model_validate(
            {
                "problem_text": "A new writing practice activity.",
                "concept_focus": "Clear claims",
                "expected_result": "Hidden answer",
            }
        )
    with pytest.raises(ValidationError):
        FeedbackPayload.model_validate(
            {
                "strengths": [],
                "guidance": ["Explain the evidence."],
                "next_step": "Revise one sentence.",
                "concepts": [],
                "verdict": "correct",
                "status": "completed",
            }
        )


@pytest.mark.parametrize("adapter", ["meta", "ollama", "vllm", "compatible"])
@pytest.mark.parametrize("purpose", ["generate", "read", "review"])
def test_new_task_schemas_use_all_http_transports(
    adapter: str, purpose: Literal["generate", "read", "review"]
) -> None:
    payload = {
        "generate": ActivityPayload(
            problem_text="Explain how you would compare two observations.", concept_focus="Evidence"
        ),
        "read": reading(),
        "review": FeedbackPayload(
            strengths=[],
            guidance=["Connect the observation to your claim."],
            next_step="Revise that connection.",
            concepts=["Evidence"],
        ),
    }[purpose]
    config = ProviderConfig.model_validate(
        {
            "adapter": adapter,
            "enabled": True,
            "model": "synthetic-tutor-v1",
            "base_url": "https://synthetic.invalid/v1"
            if adapter != "ollama"
            else "http://127.0.0.1:11434",
            "data_boundary": "cloud" if adapter == "meta" else "local_network",
            "eligibility_record": "Synthetic wire fixture",
            "capabilities": {"image_input": True, "configured_context_limit": 16384},
        }
    )
    request = ModelRequest(
        operation_id=uuid4(),
        stage="vision" if purpose == "read" else "tutor",
        purpose=purpose,
        model_id=config.model,
        system_instruction="Guide without solving supplied assignments.",
        ordered_messages=[Message(role="user", content="Synthetic practice content")],
        response_schema=type(payload).model_json_schema(),
        private_image_bytes=b"synthetic-image" if purpose == "read" else None,
    )

    def respond(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if adapter == "ollama":
            assert body["format"] == request.response_schema
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "stop",
                    "message": {"content": payload.model_dump_json()},
                },
            )
        wire_schema = body["response_format"]["json_schema"]["schema"]
        assert wire_schema == strict_response_schema(request.response_schema)
        assert set(wire_schema["required"]) == set(wire_schema["properties"])
        assert all("default" not in field for field in wire_schema["properties"].values())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": payload.model_dump_json()}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        result = HTTPProvider(config, transport).complete(request)
    assert result.validated_payload == payload
    with pytest.raises(ProviderError, match="malformed_output"):
        validate_payload(request, '{"status":"completed","verdict":"correct"}')


def test_strict_response_schema_requires_nullable_defaults_without_mutating_contract() -> None:
    schema = FeedbackPayload.model_json_schema()
    assert "uncertainty_note" not in schema["required"]
    assert schema["properties"]["uncertainty_note"]["default"] is None

    wire_schema = strict_response_schema(schema)

    assert "uncertainty_note" in wire_schema["required"]
    assert "default" not in wire_schema["properties"]["uncertainty_note"]
    assert "uncertainty_note" not in schema["required"]
    assert schema["properties"]["uncertainty_note"]["default"] is None


def test_mock_vision_only_recognizes_exact_original_public_fixture() -> None:
    fixture = Path(__file__).resolve().parents[4] / "evals/fixtures/work.png"
    request = ModelRequest(
        operation_id=uuid4(),
        stage="vision",
        purpose="read",
        model_id="fixture-v1",
        system_instruction="Read visible work.",
        ordered_messages=[Message(role="user", content="Synthetic image")],
        response_schema=ReadingPayload.model_json_schema(),
        private_image_bytes=normalize(fixture.read_bytes()),
    )
    payload = MockProvider().complete(request).validated_payload
    assert (
        isinstance(payload, ReadingPayload) and payload.transcription == "2/5" and can_read(payload)
    )
    other = (
        MockProvider()
        .complete(request.model_copy(update={"private_image_bytes": b"unrecognized"}))
        .validated_payload
    )
    assert (
        isinstance(other, ReadingPayload) and other.quality == "unreadable" and not can_read(other)
    )


def test_context_keeps_current_work_whole_and_trims_old_history() -> None:
    provider = ProviderConfig(
        adapter="mock",
        model="fixture-v1",
        enabled=True,
        data_boundary="synthetic",
        capabilities=Capabilities(configured_context_limit=2048),
    )
    messages = [
        Message(role="user", content="old" * 500),
        Message(role="assistant", content="earlier" * 100),
        Message(role="user", content="Current work kept whole"),
    ]
    result = bounded_messages(messages, "Instructions", {}, provider, image=False, output=1200)
    assert result[-1] == messages[-1] and len(result) < len(messages)
    assert result[0].role == "user"
    assert messages[1] not in result  # no feedback detached from the old work
    with pytest.raises(ProviderError, match="context_limit"):
        bounded_messages(
            [Message(role="user", content="x" * 3000)],
            "Instructions",
            {},
            provider,
            image=False,
            output=1200,
        )
    request = ModelRequest(
        operation_id=uuid4(),
        stage="tutor",
        purpose="review",
        model_id=provider.model,
        system_instruction="Instructions",
        ordered_messages=result,
        response_schema={},
    )
    check_request(provider, request)


def test_distinctness_allows_reading_excerpt_but_not_repeated_homework() -> None:
    assignment = "Explain the causes of the original historical event in the supplied worksheet."
    assert copied_reference(assignment, assignment)
    assert copied_reference(assignment, assignment + "!")
    assert not copied_reference(
        "Solve 3x + 4 = 19",
        "Practice with a different equation: solve 5x + 2 = 17 and explain your steps.",
    )
    excerpt = "The traveler closed the gate and looked back toward the quiet house."
    assert not copied_reference(
        excerpt,
        f"Read this excerpt: {excerpt} What does the action suggest about the traveler's feelings? Explain using a detail from the excerpt.",
    )
