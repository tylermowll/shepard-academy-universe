"""Killable live-provider calls with a wall-clock budget, including DNS and SDK setup."""

import json
import multiprocessing
import os
import threading
import time
from multiprocessing.connection import Connection

from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import ModelRequest, ModelResult, ProviderError
from math_tutor.adapters.providers.transports import BedrockProvider, HTTPProvider


def _call(config: ProviderConfig, request: ModelRequest, sender: Connection) -> None:
    # Bound the child even if its API/worker parent is killed during the request.
    expiry = threading.Timer(request.timeout_seconds, os._exit, args=(1,))
    expiry.daemon = True
    expiry.start()
    try:
        adapter = BedrockProvider(config) if config.adapter == "bedrock" else HTTPProvider(config)
        result = adapter.complete(request)
        sender.send_bytes(
            json.dumps({"result": result.model_dump(mode="json")}, ensure_ascii=False).encode()
        )
    except ProviderError as error:
        sender.send_bytes(
            json.dumps(
                {
                    "error": {
                        "code": error.code,
                        "retryable": error.retryable,
                        "retry_after_seconds": error.retry_after_seconds,
                        "safe_message": error.safe_message,
                        "completion_reason": error.completion_reason,
                        "http_status": error.http_status,
                    }
                }
            ).encode()
        )
    except Exception:
        # Do not send SDK exception text, provider output, or credentials to the parent.
        sender.send_bytes(b'{"error":{"code":"adapter_failure"}}')
    finally:
        expiry.cancel()
        sender.close()


def complete_bounded(config: ProviderConfig, request: ModelRequest) -> ModelResult:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_call, args=(config, request, sender), daemon=True)
    deadline = time.monotonic() + request.timeout_seconds
    try:
        process.start()
        sender.close()
        if not receiver.poll(max(0, deadline - time.monotonic())):
            raise ProviderError("timeout", True)
        message = json.loads(receiver.recv_bytes(maxlength=262144))
        if "error" in message:
            raise ProviderError(**message["error"])
        return ModelResult.model_validate(message["result"])
    except EOFError, OSError:
        raise ProviderError("unavailable", True) from None
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            # Reap our local child; a remote provider may still finish and bill its request.
            process.join(timeout=0.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            process.close()
