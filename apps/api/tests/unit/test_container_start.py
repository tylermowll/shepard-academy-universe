"""Docker discovery must never launch a second copy or inspect private settings."""

import shutil
import subprocess
from unittest.mock import Mock

import pytest

from math_tutor import container_start


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("abc123 math-practice-tutor:local\n", "abc123"),
        ("abc123 unrelated:local\n", None),
        ("abc123 math-practice-tutor:local\ndef456 math-practice-tutor:local\n", None),
        ("--privileged math-practice-tutor:local\n", None),
        ("", None),
    ],
)
def test_only_one_recognized_api_is_selected(
    monkeypatch: pytest.MonkeyPatch, output: str, expected: str | None
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    run = Mock(
        side_effect=[
            Mock(returncode=0, stdout="abc123\ndef456\n"),
            Mock(returncode=0, stdout=output),
        ]
    )
    monkeypatch.setattr(subprocess, "run", run)
    assert container_start.running_api() == expected
    arguments = run.call_args_list[0].args[0]
    assert "publish=8000" in arguments
    assert "label=com.docker.compose.service=api" in arguments
    assert run.call_args.args[0] == [
        "docker",
        "inspect",
        "--format",
        "{{.Id}} {{.Config.Image}}",
        "abc123",
        "def456",
    ]


def test_unavailable_docker_keeps_native_start_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    run = Mock(side_effect=AssertionError("Docker is not installed"))
    monkeypatch.setattr(subprocess, "run", run)
    assert container_start.running_api() is None
    run.assert_not_called()


@pytest.mark.parametrize("failure", [PermissionError(), subprocess.TimeoutExpired("docker", 5)])
def test_docker_discovery_failure_is_bounded_and_quiet(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    assert container_start.running_api() is None
    assert not capsys.readouterr().out


def test_owner_command_failure_does_not_start_or_recreate_containers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(subprocess, "run", run)
    assert container_start.connect("abc123") == 1
    run.assert_called_once_with(
        ["docker", "exec", "abc123", "python", "-m", "math_tutor.owner_setup"], check=False
    )
    assert "current image" in capsys.readouterr().out
