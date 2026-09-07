"""Synthetic wire fixtures; no requests leave the test process."""

import json
from uuid import uuid4

import boto3
import httpx2 as httpx
import pytest
from botocore.stub import Stubber
from pydantic import ValidationError

from math_tutor.adapters.providers.config import Configuration, ProviderConfig, Routes, route
from math_tutor.adapters.providers.contracts import (
    Capabilities,
    InterpretationPayload,
    Message,
    ModelRequest,
    ProviderError,
    TutorPayload,
)
from math_tutor.adapters.providers.transports import BedrockProvider, HTTPProvider, validate_payload

PAYLOAD = {
    "schema_version": "1",
    "message_kind": "question_response",
    "message_markdown": "Use equal-sized parts.",
    "suggested_next_action": "revise_answer",
    "uncertainty_note": None,
}


def request(image: bool = False) -> ModelRequest:
    return ModelRequest(
        operation_id=uuid4(),
        stage="vision" if image else "tutor",
        model_id="synthetic-model-v1",
        system_instruction="Return the JSON schema.",
        ordered_messages=[Message(role="user", content="Synthetic fraction question")],
        private_image_bytes=b"synthetic-png-bytes" if image else None,
        response_schema=(InterpretationPayload if image else TutorPayload).model_json_schema(),
    )


@pytest.mark.parametrize("adapter", ["meta", "ollama", "vllm", "compatible"])
def test_transport_maps_roles_schema_and_private_image(adapter: str) -> None:
    config = ProviderConfig.model_validate(
        {
            "adapter": adapter,
            "model": "synthetic-model-v1",
            "enabled": True,
            "base_url": "https://synthetic.invalid/v1"
            if adapter != "ollama"
            else "http://127.0.0.1:11434",
            "data_boundary": "cloud" if adapter == "meta" else "local_network",
            "eligibility_record": "Synthetic fixture only",
            "capabilities": {"image_input": True},
        }
    )
    captured = []

    def respond(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        captured.append(body)
        assert body["messages"][0]["role"] == "system"
        if adapter == "ollama":
            assert req.url.path == "/api/chat"
            assert body["messages"][-1]["images"] == ["c3ludGhldGljLXBuZy1ieXRlcw=="]
            assert body["format"] == request(True).response_schema
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "stop",
                    "message": {"content": json.dumps({"transcription": "2/5", "ambiguities": []})},
                    "eval_count": 4,
                },
            )
        assert req.url.path == "/v1/chat/completions"
        assert body["messages"][-1]["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        assert body["response_format"]["json_schema"]["schema"] == request(True).response_schema
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"transcription": "2/5", "ambiguities": []})
                        },
                    }
                ],
                "usage": {"completion_tokens": 4},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = HTTPProvider(config, client).complete(request(True))
    assert isinstance(result.validated_payload, InterpretationPayload)
    assert result.validated_payload.transcription == "2/5"
    assert len(captured) == 1


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(429, headers={"Retry-After": "3"}), "throttled", True),
        (httpx.Response(401), "authentication", False),
        (
            httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"refusal": "no", "content": ""}}
                    ]
                },
            ),
            "refusal",
            False,
        ),
        (httpx.Response(200, json={"choices": []}), "malformed_output", False),
        (httpx.Response(302, headers={"Location": "https://other.invalid"}), "unavailable", False),
    ],
)
def test_errors_are_typed_and_never_retried(
    response: httpx.Response, code: str, retryable: bool
) -> None:
    config = ProviderConfig(
        adapter="compatible",
        model="synthetic-model-v1",
        enabled=True,
        base_url="https://synthetic.invalid/v1",
        eligibility_record="Synthetic only",
    )
    calls: list[httpx.Request] = []

    def respond(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return response

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(ProviderError) as error,
    ):
        HTTPProvider(config, client).complete(request())
    assert error.value.code == code and error.value.retryable == retryable
    assert len(calls) == 1


def test_schema_does_not_accept_model_verdict_or_prose() -> None:
    for output in (
        "Here is JSON: " + json.dumps(PAYLOAD),
        json.dumps({**PAYLOAD, "answer_status": "correct"}),
        "{}",
    ):
        with pytest.raises(ProviderError):
            validate_payload(request(), output)


def test_bedrock_converse_uses_sdk_schema_and_image_blocks() -> None:
    config = ProviderConfig(
        adapter="bedrock",
        model="synthetic-model-v1",
        region="us-east-1",
        enabled=True,
        data_boundary="cloud",
        eligibility_record="Synthetic stub",
        capabilities=Capabilities(image_input=True),
    )
    client = boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    adapter = BedrockProvider(config, client)
    body = adapter.wire(request(True))
    assert body["messages"][-1]["content"][-1]["image"]["source"]["bytes"] == b"synthetic-png-bytes"
    assert "outputConfig" in body and "response_format" not in body
    with Stubber(client) as stub:
        stub.add_response(
            "converse",
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": '{"transcription":"2/5","ambiguities":[]}'}],
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 6, "totalTokens": 16},
                "metrics": {"latencyMs": 1},
            },
            body,
        )
        result = adapter.complete(request(True))
    assert result.reported_usage["totalTokens"] == 16
    client.close()


@pytest.mark.parametrize("eligibility", ["minor", "unknown", "adult"])
def test_meta_blocks_mixed_and_unknown_audiences(
    monkeypatch: pytest.MonkeyPatch, eligibility: str
) -> None:
    provider = ProviderConfig(
        adapter="meta",
        model="synthetic-model-v1",
        enabled=True,
        base_url="https://synthetic.invalid/v1",
        data_boundary="cloud",
        audience="adult_only",
        eligibility_record="synthetic",
    )
    config = Configuration(routes=Routes(tutor="meta", vision="meta"), providers={"meta": provider})
    monkeypatch.setenv("ALLOW_CLOUD_INFERENCE", "true")
    monkeypatch.setenv("APP_AUDIENCE", "mixed")
    with pytest.raises(ProviderError):
        route(config, "tutor", eligibility)
    monkeypatch.setenv("APP_AUDIENCE", "adult_only")
    if eligibility == "adult":
        assert route(config, "tutor", eligibility)[0] == "meta"
    else:
        with pytest.raises(ProviderError):
            route(config, "tutor", eligibility)


def test_invalid_config_and_image_capability_fail_closed() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="meta",
            model="x",
            enabled=True,
            base_url="http://bad.invalid",
            data_boundary="cloud",
        )
    provider = ProviderConfig(
        adapter="ollama",
        model="synthetic-model-v1",
        enabled=True,
        base_url="http://127.0.0.1:11434",
        eligibility_record="synthetic",
    )
    with pytest.raises(ProviderError) as error:
        HTTPProvider(provider).complete(request(True))
    assert error.value.code == "unsupported_modality"


def test_s3_private_object_mapping() -> None:
    from io import BytesIO

    from botocore.response import StreamingBody

    from math_tutor.adapters.cloud_storage import S3Storage

    key = uuid4()
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    store = S3Storage("synthetic-private-bucket", "us-east-1", client)
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "synthetic-private-bucket",
                "Key": "objects/" + str(key),
                "Body": b"synthetic",
                "ServerSideEncryption": "AES256",
                "ContentType": "application/octet-stream",
                "CacheControl": "no-store",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(b"synthetic"), 9), "ContentLength": 9},
            {"Bucket": "synthetic-private-bucket", "Key": "objects/" + str(key)},
        )
        stub.add_response(
            "delete_object",
            {},
            {"Bucket": "synthetic-private-bucket", "Key": "objects/" + str(key)},
        )
        store.put(key, b"synthetic")
        assert store.get(key) == b"synthetic"
        store.delete(key)
    store.close()


def test_route_rejects_disabled_text_capability() -> None:
    from math_tutor.adapters.providers.config import Configuration, route

    config = Configuration()
    provider = config.providers["demo"]
    config = config.model_copy(
        update={
            "providers": {
                "demo": provider.model_copy(
                    update={
                        "capabilities": provider.capabilities.model_copy(
                            update={"text_input": False}
                        )
                    }
                )
            }
        }
    )
    with pytest.raises(ProviderError, match="unsupported_modality"):
        route(config, "tutor", "adult")
