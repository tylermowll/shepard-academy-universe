"""Native gateway launch contract, without starting services or reading private config."""

import os
import runpy
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

LAUNCHER = Path(__file__).resolve().parents[4] / "scripts" / "dev.py"


@pytest.mark.parametrize(
    ("origin", "arguments", "message"),
    [
        ("http://127.0.0.1:8000", ["--gateway"], "requires APP_PUBLIC_ORIGIN=https"),
        ("https://tutor.example", [], "make dev is loopback only"),
        ("http://192.168.1.12:8000", ["--gateway"], "HTTP only on loopback"),
    ],
)
def test_launcher_rejects_unsafe_or_wrong_mode_origins(
    monkeypatch: pytest.MonkeyPatch, origin: str, arguments: list[str], message: str
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "synthetic-launcher-session-secret-" * 2)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", origin)
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER), *arguments])
    start = Mock()
    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises((SystemExit, ValueError), match=message):
        runpy.run_path(str(LAUNCHER), run_name="__main__")
    start.assert_not_called()


@pytest.mark.parametrize(
    ("origin", "arguments", "port"),
    [
        ("https://tutor.example", ["--gateway"], "8000"),
        ("http://127.0.0.1:8012", [], "8012"),
    ],
)
def test_launcher_binds_loopback_supervises_worker_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, origin: str, arguments: list[str], port: str
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "synthetic-launcher-session-secret-" * 2)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", origin)
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER), *arguments])
    monkeypatch.setattr(signal, "signal", Mock())
    api, worker = Mock(), Mock()
    api.poll.return_value = 0  # Simulate one service exiting: stop the other too.
    start = Mock(side_effect=[api, worker])
    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises(SystemExit, match="A service exited"):
        runpy.run_path(str(LAUNCHER), run_name="__main__")
    api_command = start.call_args_list[0].args[0]
    assert api_command == [
        sys.executable,
        "-m",
        "uvicorn",
        "math_tutor.api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        port,
        "--no-proxy-headers",
        "--no-access-log",
    ]
    assert start.call_args_list[1].args[0] == [sys.executable, "-m", "math_tutor.worker"]
    for process in (api, worker):
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=10)


@pytest.mark.parametrize("mode", ["private", "demo"])
def test_supervisor_passes_owner_token_only_to_private_api(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    token = "synthetic-owner-setup-token-only"
    monkeypatch.setenv("SESSION_SECRET", "synthetic-launcher-session-secret-" * 2)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "http://127.0.0.1:8000")
    monkeypatch.setenv("APP_MODE", mode)
    monkeypatch.setenv("SHEPARD_SETUP_TOKEN", token)
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER)])
    monkeypatch.setattr(signal, "signal", Mock())
    api, worker = Mock(), Mock()
    api.poll.return_value = 0
    start = Mock(side_effect=[api, worker])
    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises(SystemExit, match="A service exited"):
        runpy.run_path(str(LAUNCHER), run_name="__main__")
    assert start.call_args_list[0].kwargs["env"].get("SHEPARD_SETUP_TOKEN") == (
        token if mode == "private" else None
    )
    assert "SHEPARD_SETUP_TOKEN" not in start.call_args_list[1].kwargs["env"]
    assert "SHEPARD_SETUP_TOKEN" not in os.environ
    assert token not in capsys.readouterr().out
