"""Synthetic wire fixtures; no requests leave the test process."""

import json
import socket
from typing import Any
from uuid import uuid4

import boto3
import httpx2 as httpx
import pytest
from botocore.exceptions import NoCredentialsError
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
from math_tutor.adapters.providers.transports import (
    BedrockProvider,
    HTTPProvider,
    pinned_endpoints,
    validate_payload,
)

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
                "usage": {
                    "inputTokens": 10,
                    "outputTokens": 6,
                    "totalTokens": 16,
                    "cacheReadInputTokens": 4,
                    "cacheWriteInputTokens": 2,
                    "cacheDetails": [],
                },
                "metrics": {"latencyMs": 1},
            },
            body,
        )
        result = adapter.complete(request(True))
    assert result.reported_usage["totalTokens"] == 16
    assert result.reported_usage["cacheReadInputTokens"] == 4
    assert result.reported_usage["cacheWriteInputTokens"] == 2
    assert "cacheDetails" not in result.reported_usage
    client.close()


@pytest.mark.parametrize("eligibility", ["minor", "unknown", "adult"])
def test_meta_mixed_audience_routes_under_cloud_policy(
    monkeypatch: pytest.MonkeyPatch, eligibility: str
) -> None:
    provider = ProviderConfig(
        adapter="meta",
        model="synthetic-model-v1",
        enabled=True,
        base_url="https://synthetic.invalid/v1",
        data_boundary="cloud",
        audience="mixed",
        eligibility_record="synthetic",
    )
    config = Configuration(routes=Routes(tutor="meta", vision="meta"), providers={"meta": provider})
    monkeypatch.setenv("ALLOW_CLOUD_INFERENCE", "true")
    monkeypatch.setenv("APP_AUDIENCE", "mixed")
    assert route(config, "tutor", eligibility)[0] == "meta"


def test_meta_selected_restricted_audience_uses_general_routing_policy(
    monkeypatch: pytest.MonkeyPatch,
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
    with pytest.raises(ProviderError, match="audience_blocked"):
        route(config, "tutor", "adult")
    monkeypatch.setenv("APP_AUDIENCE", "adult_only")
    assert route(config, "tutor", "adult")[0] == "meta"
    with pytest.raises(ProviderError, match="audience_blocked"):
        route(config, "tutor", "minor")


def test_meta_rejects_local_data_boundary() -> None:
    with pytest.raises(ValidationError, match="cloud data boundary"):
        ProviderConfig(
            adapter="meta",
            model="synthetic-model-v1",
            enabled=True,
            base_url="https://synthetic.invalid/v1",
            data_boundary="local_network",
            audience="mixed",
            eligibility_record="synthetic",
        )


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


@pytest.mark.parametrize(
    ("adapter", "body"),
    [
        ("compatible", []),
        ("compatible", {"choices": [None]}),
        ("compatible", {"choices": [{"finish_reason": "stop", "message": None}]}),
        ("compatible", {"choices": [{"finish_reason": [], "message": {"content": "{}"}}]}),
        (
            "compatible",
            {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}], "usage": None},
        ),
        ("ollama", []),
        ("ollama", {"done": True, "message": None}),
        ("ollama", {"done": True, "done_reason": [], "message": {"content": "{}"}}),
    ],
)
def test_malformed_wire_envelopes_are_safe_failures(adapter: str, body: Any) -> None:
    config = ProviderConfig.model_validate(
        {
            "adapter": adapter,
            "model": "synthetic-model-v1",
            "enabled": True,
            "base_url": "http://127.0.0.1:11434",
            "eligibility_record": "Synthetic fixture",
        }
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ) as client,
        pytest.raises(ProviderError, match="malformed_output") as error,
    ):
        HTTPProvider(config, client).complete(request())
    assert not error.value.retryable


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"stopReason": []},
        {"stopReason": "end_turn", "output": {"message": None}},
        {"stopReason": "end_turn", "usage": None},
        {"stopReason": "end_turn", "metrics": None},
    ],
)
def test_malformed_bedrock_envelopes_are_safe_failures(
    body: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    monkeypatch.setattr(client, "converse", lambda **_: body)
    config = ProviderConfig(
        adapter="bedrock",
        model="synthetic-model-v1",
        region="us-east-1",
        enabled=True,
        data_boundary="cloud",
        eligibility_record="Synthetic stub",
    )
    try:
        with pytest.raises(ProviderError, match="malformed_output"):
            BedrockProvider(config, client).complete(request())
    finally:
        client.close()


def test_bedrock_client_setup_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise NoCredentialsError()

    monkeypatch.setattr(boto3, "client", unavailable)
    config = ProviderConfig(
        adapter="bedrock",
        model="synthetic-model-v1",
        region="us-east-1",
        enabled=True,
        data_boundary="cloud",
        eligibility_record="Synthetic stub",
    )
    with pytest.raises(ProviderError, match="unavailable"):
        BedrockProvider(config).complete(request())


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254",
        "http://[fe80::1]",
        "http://[fd00:ec2::254]",
        "http://[fd00:ec2::254%25lo]",
        "http://[::ffff:169.254.169.254]",
        "http://metadata.google.internal",
        "http://instance-data.ec2.internal",
        "http://0.0.0.0",
        "http://127.0.0.1:0",
    ],
)
def test_metadata_and_invalid_destinations_are_rejected(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="compatible",
            model="synthetic-model-v1",
            enabled=True,
            base_url=endpoint,
            eligibility_record="Synthetic fixture",
        )


def test_resolved_metadata_is_blocked_and_allowed_address_is_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolved(address: str) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]

    url = httpx.URL("https://synthetic.invalid/v1/chat/completions")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: resolved("169.254.169.254"))
    with pytest.raises(ProviderError, match="invalid_endpoint"):
        pinned_endpoints(url)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: resolved("192.168.1.10"))
    [pinned] = pinned_endpoints(url)
    assert pinned.host == "192.168.1.10"
    assert pinned.path == url.path and pinned.scheme == "https"


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111"])
def test_local_boundary_cannot_resolve_to_public_internet(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
        ],
    )
    with pytest.raises(ProviderError, match="invalid_endpoint"):
        pinned_endpoints(httpx.URL("https://synthetic.invalid/v1"), local_only=True)


@pytest.mark.parametrize(
    ("failure", "expected_attempts", "expected_error"),
    [
        (httpx.ConnectError, 2, None),
        (httpx.ConnectTimeout, 2, None),
        (httpx.ReadTimeout, 1, "timeout"),
        (httpx.WriteError, 1, "unavailable"),
        (httpx.RemoteProtocolError, 1, "unavailable"),
    ],
)
def test_pinned_connections_preserve_authority_and_only_retry_connect_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[httpx.RequestError],
    expected_attempts: int,
    expected_error: str | None,
) -> None:
    answers = [
        (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("::1", 8443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8443)),
    ]
    resolutions = []

    def resolve(host: str, port: int, **kwargs: Any) -> Any:
        resolutions.append((host, port))
        return answers

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    calls: list[httpx.Request] = []

    def respond(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["Host"] == "synthetic.invalid:8443"
        assert req.extensions["sni_hostname"] == "synthetic.invalid"
        assert req.url.path == "/v1/chat/completions"
        if len(calls) == 1:
            assert req.url.host == "::1"
            raise failure("Synthetic transport failure", request=req)
        assert req.url.host == "127.0.0.1"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(PAYLOAD)}}]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    # Exercise the production resolution/pinning path with an in-process transport.
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    config = ProviderConfig(
        adapter="compatible",
        model="synthetic-model-v1",
        enabled=True,
        base_url="https://synthetic.invalid:8443/v1",
        eligibility_record="Synthetic fixture",
    )
    if expected_error is None:
        result = HTTPProvider(config).complete(request())
        assert isinstance(result.validated_payload, TutorPayload)
        assert result.validated_payload.message_markdown == PAYLOAD["message_markdown"]
    else:
        with pytest.raises(ProviderError, match=expected_error):
            HTTPProvider(config).complete(request())
    assert len(calls) == expected_attempts
    assert resolutions == [("synthetic.invalid", 8443)]
    assert client.is_closed
