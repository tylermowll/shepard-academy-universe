"""Production subprocess provider calls against a synthetic loopback HTTP peer."""

import ctypes
import json
import multiprocessing
import os
import signal
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing.connection import Connection
from queue import Queue
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr

from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import (
    Message,
    ModelRequest,
    ProviderError,
    TutorPayload,
)
from math_tutor.providers import complete


@dataclass(frozen=True)
class LoopbackProvider:
    base_url: str
    requests: Queue[dict[str, Any]]
    chunks_sent: Queue[int]
    authorization: Queue[str | None]


@pytest.fixture
def loopback() -> Iterator[LoopbackProvider]:
    requests: Queue[dict[str, Any]] = Queue()
    chunks_sent: Queue[int] = Queue()
    authorization: Queue[str | None] = Queue()
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            authorization.put(self.headers.get("Authorization"))
            requests.put(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            message = "Use equal-sized parts before adding fractions."
            if self.path.startswith("/unicode/"):
                message = "\U0001f4d0" * 6000
            payload = {
                "message_kind": "question_response",
                "message_markdown": message,
                "suggested_next_action": "revise_answer",
            }
            body = {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(payload, ensure_ascii=False)},
                    }
                ],
                "usage": {"prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 20},
            }
            if self.path.startswith("/malformed/"):
                body["choices"] = [{"finish_reason": "stop", "message": None}]
            encoded = json.dumps(body).encode()
            slow = self.path.startswith("/slow/")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded) + (40 if slow else 0)))
            self.end_headers()
            try:
                if slow:
                    # Every read receives data well inside its one-second timeout.
                    # The whole response takes six seconds without an overall deadline.
                    for index in range(40):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        chunks_sent.put(index)
                        if stop.wait(0.15):
                            return
                self.wfile.write(encoded)
                self.wfile.flush()
            except BrokenPipeError, ConnectionResetError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LoopbackProvider(
            f"http://127.0.0.1:{server.server_port}", requests, chunks_sent, authorization
        )
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def provider(loopback: LoopbackProvider, path: str = "normal") -> ProviderConfig:
    return ProviderConfig(
        adapter="compatible",
        model="synthetic-execution-v1",
        enabled=True,
        base_url=f"{loopback.base_url}/{path}",
        data_boundary="local_network",
        audience="mixed",
        eligibility_record="Synthetic loopback fixture only; no model inference.",
    )


def request(timeout_seconds: int = 5) -> ModelRequest:
    return ModelRequest(
        operation_id=uuid4(),
        stage="tutor",
        model_id="synthetic-execution-v1",
        system_instruction="Answer the synthetic fraction question.",
        ordered_messages=[Message(role="user", content="Why do the parts need equal sizes?")],
        response_schema=TutorPayload.model_json_schema(),
        timeout_seconds=timeout_seconds,
    )


@pytest.mark.parametrize("in_thread", [False, True], ids=["worker", "api-thread"])
def test_provider_result_round_trips_from_child(
    loopback: LoopbackProvider, in_thread: bool
) -> None:
    existing_children = {child.pid for child in multiprocessing.active_children()}
    config, work = provider(loopback), request()
    if in_thread:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(complete, config, work).result(timeout=8)
    else:
        result = complete(config, work)
    assert isinstance(result.validated_payload, TutorPayload)
    assert result.validated_payload.message_markdown == (
        "Use equal-sized parts before adding fractions."
    )
    assert result.model_id == work.model_id
    assert result.reported_usage == {
        "prompt_tokens": 13,
        "completion_tokens": 7,
        "total_tokens": 20,
    }
    wire = loopback.requests.get_nowait()
    assert wire["model"] == work.model_id
    assert wire["messages"][-1] == work.ordered_messages[-1].model_dump()
    assert {child.pid for child in multiprocessing.active_children()} <= existing_children


def test_unicode_result_fits_bounded_child_channel(loopback: LoopbackProvider) -> None:
    result = complete(provider(loopback, "unicode"), request())
    assert isinstance(result.validated_payload, TutorPayload)
    assert result.validated_payload.message_markdown == "\U0001f4d0" * 6000


def test_write_only_key_reaches_real_http_child_without_serialization_leak(
    loopback: LoopbackProvider,
) -> None:
    key = "synthetic-provider-credential-for-loopback-only"
    config = provider(loopback).model_copy(update={"api_key_secret": SecretStr(key)})
    assert key not in config.model_dump_json() and key not in repr(config)
    result = complete(config, request())
    assert loopback.authorization.get_nowait() == "Bearer " + key
    assert key not in result.model_dump_json()
    assert key not in json.dumps(loopback.requests.get_nowait())


def test_total_timeout_stops_a_child_receiving_regular_chunks(loopback: LoopbackProvider) -> None:
    existing_children = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(ProviderError) as caught:
        complete(provider(loopback, "slow"), request(timeout_seconds=1))
    elapsed = time.monotonic() - started
    assert caught.value.code == "timeout" and caught.value.retryable
    assert elapsed < 2.5, f"One-second provider call remained active for {elapsed:.2f}s"
    assert loopback.chunks_sent.qsize() >= 2, "The server must actually be sending regular data"
    assert {child.pid for child in multiprocessing.active_children()} <= existing_children


def test_malformed_response_does_not_poison_the_next_call(loopback: LoopbackProvider) -> None:
    existing_children = {child.pid for child in multiprocessing.active_children()}
    with pytest.raises(ProviderError) as caught:
        complete(provider(loopback, "malformed"), request())
    assert caught.value.code == "malformed_output"
    assert {child.pid for child in multiprocessing.active_children()} <= existing_children
    result = complete(provider(loopback), request())
    assert isinstance(result.validated_payload, TutorPayload)
    assert result.validated_payload.message_kind == "question_response"
    assert loopback.requests.qsize() == 2
    assert {child.pid for child in multiprocessing.active_children()} <= existing_children


def _watched_parent(config: ProviderConfig, work: ModelRequest, control: Connection) -> None:
    def report_child() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            children = multiprocessing.active_children()
            if children:
                control.send(children[0].pid)
                control.close()
                return
            time.sleep(0.01)

    watcher = threading.Thread(target=report_child, daemon=True)
    watcher.start()
    with suppress(ProviderError):
        complete(config, work)


def _orphan_supervisor(config: ProviderConfig, work: ModelRequest, control: Connection) -> None:
    # A disposable Linux subreaper owns the orphan, so the test leaves no zombie
    # behind and never changes the pytest process's child-reaping behavior.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        control.send(("subreaper_failed", ctypes.get_errno()))
        control.close()
        return
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    parent = context.Process(target=_watched_parent, args=(config, work, writer))
    child_pid: int | None = None
    try:
        parent.start()
        writer.close()
        if not reader.poll(8):
            control.send(("child_not_started", None))
            return
        child_pid = reader.recv()
        control.send(("started", child_pid))
        if not control.poll(8) or control.recv() != "kill_parent":
            return
        parent.kill()
        parent.join(timeout=2)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            assert child_pid is not None
            reaped, status = os.waitpid(child_pid, os.WNOHANG)
            if reaped:
                child_pid = None
                control.send(("reaped", os.waitstatus_to_exitcode(status)))
                return
            time.sleep(0.02)
        control.send(("watchdog_did_not_exit", child_pid))
    finally:
        reader.close()
        writer.close()
        if parent.pid is not None:
            if parent.is_alive():
                parent.kill()
            parent.join(timeout=2)
            parent.close()
        if child_pid is not None:
            with suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGKILL)
            with suppress(ChildProcessError):
                os.waitpid(child_pid, 0)
        control.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper isolates orphan cleanup")
def test_provider_child_expires_and_is_reaped_after_parent_death(
    loopback: LoopbackProvider,
) -> None:
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe()
    supervisor = context.Process(
        target=_orphan_supervisor,
        args=(provider(loopback, "slow"), request(timeout_seconds=2), writer),
    )
    supervisor.start()
    writer.close()
    try:
        assert reader.poll(8), "The disposable parent did not report its provider child"
        state, child_pid = reader.recv()
        assert state == "started" and isinstance(child_pid, int)
        loopback.chunks_sent.get(timeout=5)
        started = time.monotonic()
        reader.send("kill_parent")
        assert reader.poll(5), "The orphan provider child outlived its deadline"
        assert reader.recv() == ("reaped", 1)
        assert time.monotonic() - started < 3
    finally:
        # Abort also lets the supervisor clean up after any earlier assertion fails.
        with suppress(BrokenPipeError):
            reader.send("abort")
        supervisor.join(timeout=5)
        if supervisor.is_alive():
            supervisor.kill()
            supervisor.join(timeout=2)
        assert supervisor.exitcode == 0
        supervisor.close()
        reader.close()
