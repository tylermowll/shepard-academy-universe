"""Local startup routing without operator settings, databases, builds, or services."""

import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from math_tutor import cli, container_start, local_start, settings


@pytest.fixture(autouse=True)
def no_live_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_start, "running_api", Mock(return_value=None))


def test_running_docker_renews_setup_without_native_settings_database_or_build(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container_start, "running_api", Mock(return_value="abc123"))
    connect = Mock(return_value=0)
    monkeypatch.setattr(container_start, "connect", connect)
    forbidden = Mock(side_effect=AssertionError("Docker must not start a native installation"))
    monkeypatch.setattr(local_start, "load_environment", forbidden)
    monkeypatch.setattr(local_start, "start_services", forbidden)
    monkeypatch.setattr(cli, "run_setup", forbidden)
    assert local_start.main(["--env-file", str(synthetic_root / ".env")]) == 0
    connect.assert_called_once_with("abc123")
    forbidden.assert_not_called()
    assert not (synthetic_root / ".env").exists()
    assert not (synthetic_root / "data").exists()


def test_explicit_alternate_settings_do_not_connect_to_docker(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    discover = Mock(side_effect=AssertionError("Alternate installation must remain explicit"))
    monkeypatch.setattr(container_start, "running_api", discover)
    monkeypatch.setattr(local_start, "start_services", Mock(return_value=0))
    assert local_start.main(["--env-file", str(synthetic_root / "alternate.env")]) == 0
    discover.assert_not_called()


@pytest.mark.parametrize("mode", ["--gateway", "--loopback"])
def test_explicit_native_mode_does_not_connect_to_docker(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    discover = Mock(side_effect=AssertionError("Explicit native modes must validate their origin"))
    monkeypatch.setattr(container_start, "running_api", discover)
    monkeypatch.setattr(local_start, "start_services", Mock(return_value=0))
    if mode == "--gateway":
        monkeypatch.setenv("APP_PUBLIC_ORIGIN", "https://tutor.example")
    assert local_start.main([mode]) == 0
    discover.assert_not_called()


@pytest.fixture
def synthetic_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "repository_root", lambda: tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'data/test.sqlite3'}")
    monkeypatch.setenv("SESSION_SECRET", "synthetic-startup-session-secret-" * 2)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "http://127.0.0.1:8000")
    monkeypatch.setattr(local_start, "load_environment", Mock(return_value={}))
    monkeypatch.setattr(local_start, "owner_setup_token", Mock(return_value=None))
    return tmp_path


def test_first_run_creates_private_settings_then_loads_them_without_disclosing_values(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    load = Mock(return_value={})
    start = Mock(return_value=0)
    monkeypatch.setattr(local_start, "load_environment", load)
    monkeypatch.setattr(local_start, "start_services", start)
    assert local_start.main(["--uv", "/tools/uv"]) == 0
    destination = synthetic_root / ".env"
    assert destination.stat().st_mode & 0o777 == 0o600
    contents = destination.read_text()
    assert "SESSION_SECRET=" in contents
    secret_line = next(line for line in contents.splitlines() if line.startswith("SESSION_SECRET="))
    assert secret_line.split("=", 1)[1] not in capsys.readouterr().out
    load.assert_called_once_with(destination, synthetic_root, "/tools/uv")
    start.assert_called_once()


def test_restart_keeps_existing_file_and_passes_gateway_mode(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = synthetic_root / "alternate.env"
    destination.write_text("SYNTHETIC_SETTING='never execute $(whoami)'\n")
    destination.chmod(0o600)
    before = destination.read_bytes()
    setup = Mock(side_effect=AssertionError("Existing settings must not be regenerated"))
    start = Mock(return_value=0)
    monkeypatch.setattr(cli, "run_setup", setup)
    monkeypatch.setattr(local_start, "start_services", start)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "https://tutor.example")
    assert local_start.main(["--env-file", str(destination), "--gateway"]) == 0
    setup.assert_not_called()
    assert destination.read_bytes() == before
    assert start.call_args.args[1].scheme == "https"


def test_world_readable_settings_fail_without_loading_or_changing_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / ".env"
    destination.write_text("SYNTHETIC_SECRET=not-printed\n")
    destination.chmod(0o644)
    parse = Mock()
    monkeypatch.setattr(subprocess, "run", parse)
    with pytest.raises(ValueError, match="permissions 600"):
        local_start.load_environment(destination, tmp_path, "uv")
    parse.assert_not_called()
    assert destination.stat().st_mode & 0o777 == 0o644


def test_missing_secret_fails_before_database_setup_or_build(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SESSION_SECRET")
    start = Mock()
    monkeypatch.setattr(local_start, "start_services", start)
    assert local_start.main([]) == 1
    start.assert_not_called()
    assert "SESSION_SECRET" in capsys.readouterr().err
    assert not (synthetic_root / "data").exists()


@pytest.mark.parametrize(
    ("origin", "arguments", "message"),
    [
        ("http://127.0.0.1:8000", ["--gateway"], "requires APP_PUBLIC_ORIGIN=https"),
        ("https://tutor.example", ["--loopback"], "make dev is loopback only"),
        ("http://192.168.1.2:8000", [], "HTTP only on loopback"),
    ],
)
def test_wrong_origin_fails_before_build(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    origin: str,
    arguments: list[str],
    message: str,
) -> None:
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", origin)
    start = Mock()
    monkeypatch.setattr(local_start, "start_services", start)
    assert local_start.main(arguments) == 1
    start.assert_not_called()
    assert message in capsys.readouterr().err


def test_native_lock_rejects_competing_launcher_and_can_be_reacquired(tmp_path: Path) -> None:
    database = tmp_path / "private/test.sqlite3"
    with (
        local_start.native_lock(database),
        pytest.raises(ValueError, match="already has a running native app"),
        local_start.native_lock(database),
    ):
        pytest.fail("Competing launcher acquired the lock")
    with local_start.native_lock(database):
        assert not database.exists()
    assert (database.parent / ".test.sqlite3.native.lock").stat().st_mode & 0o777 == 0o600


def test_setup_then_build_then_https_supervisor_order(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(local_start, "native_lock", lambda _: nullcontext())
    monkeypatch.setattr(local_start, "check_port", lambda _: calls.append("port"))
    monkeypatch.setattr(local_start, "prepare_database", lambda _: calls.append("database"))

    def owner(_origin: object) -> None:
        calls.append("owner-check")

    monkeypatch.setattr(local_start, "owner_setup_token", owner)
    monkeypatch.setattr(
        "builtins.input", Mock(side_effect=AssertionError("No native signup prompt"))
    )
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subprocess, "run", launch)
    assert (
        local_start.start_services(synthetic_root, urlsplit("https://tutor.example"), "make") == 0
    )
    assert calls == ["port", "database", "owner-check"]
    assert launch.call_args_list[0].args[0] == ["make", "toolchain-check"]
    assert launch.call_args_list[1].args[0] == ["make", "build"]
    assert launch.call_args_list[2].args[0] == [
        sys.executable,
        str(synthetic_root / "scripts/dev.py"),
        "--gateway",
    ]


def test_owner_policy_rejection_never_builds_or_starts_services(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_start, "native_lock", lambda _: nullcontext())
    monkeypatch.setattr(local_start, "check_port", Mock())
    monkeypatch.setattr(local_start, "prepare_database", Mock())
    monkeypatch.setattr(
        local_start,
        "owner_setup_token",
        Mock(side_effect=ValueError("Use make admin before HTTPS")),
    )
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subprocess, "run", launch)
    with pytest.raises(ValueError, match="make admin"):
        local_start.start_services(synthetic_root, urlsplit("https://tutor.example"), "make")
    launch.assert_called_once_with(["make", "toolchain-check"], cwd=synthetic_root, check=False)


def test_failed_build_never_starts_services_or_prints_owner_token(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local_start, "native_lock", lambda _: nullcontext())
    monkeypatch.setattr(local_start, "check_port", Mock())
    monkeypatch.setattr(local_start, "prepare_database", Mock())
    monkeypatch.setattr(
        local_start, "owner_setup_token", Mock(return_value="synthetic-unprinted-owner-token")
    )
    launch = Mock(side_effect=[Mock(returncode=0), Mock(returncode=2)])
    monkeypatch.setattr(subprocess, "run", launch)
    assert (
        local_start.start_services(synthetic_root, urlsplit("http://127.0.0.1:8000"), "make") == 2
    )
    assert launch.call_count == 2
    assert launch.call_args.args[0] == ["make", "build"]
    assert "synthetic-unprinted-owner-token" not in capsys.readouterr().out


def test_failed_toolchain_never_touches_database_or_password_prompt(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare = Mock()
    admin = Mock()
    monkeypatch.setattr(local_start, "prepare_database", prepare)
    monkeypatch.setattr(local_start, "owner_setup_token", admin)
    launch = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(subprocess, "run", launch)
    assert (
        local_start.start_services(synthetic_root, urlsplit("http://127.0.0.1:8000"), "make") == 1
    )
    prepare.assert_not_called()
    admin.assert_not_called()
    assert not (synthetic_root / "data").exists()
    launch.assert_called_once_with(["make", "toolchain-check"], cwd=synthetic_root, check=False)


def test_unclaimed_native_start_prints_fragment_link_and_never_prompts(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "synthetic-owner-token-" * 3
    monkeypatch.setenv(local_start.SETUP_TOKEN_ENV, "stale-inherited-token")
    monkeypatch.setattr(local_start, "native_lock", lambda _: nullcontext())
    monkeypatch.setattr(local_start, "check_port", Mock())
    monkeypatch.setattr(local_start, "prepare_database", Mock())
    monkeypatch.setattr(local_start, "owner_setup_token", Mock(return_value=token))
    prompt = Mock(side_effect=AssertionError("Account setup belongs in the browser"))
    monkeypatch.setattr("builtins.input", prompt)
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subprocess, "run", launch)
    assert (
        local_start.start_services(synthetic_root, urlsplit("http://127.0.0.1:8000"), "make") == 0
    )
    prompt.assert_not_called()
    assert local_start.SETUP_TOKEN_ENV not in os.environ
    assert launch.call_args.kwargs["env"][local_start.SETUP_TOKEN_ENV] == token
    for call in launch.call_args_list:
        assert token not in " ".join(call.args[0])
    output = capsys.readouterr().out
    assert output.count(token) == 1
    assert f"http://127.0.0.1:8000/#setup={token}" in output
    assert "30 minutes" in output
    assert "stale-inherited-token" not in output


def test_claimed_native_start_drops_stale_token_and_omits_setup_link(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(local_start.SETUP_TOKEN_ENV, "stale-inherited-token")
    monkeypatch.setattr(local_start, "native_lock", lambda _: nullcontext())
    monkeypatch.setattr(local_start, "check_port", Mock())
    monkeypatch.setattr(local_start, "prepare_database", Mock())
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subprocess, "run", launch)
    assert (
        local_start.start_services(synthetic_root, urlsplit("http://127.0.0.1:8000"), "make") == 0
    )
    assert local_start.SETUP_TOKEN_ENV not in launch.call_args.kwargs["env"]
    assert "#setup=" not in capsys.readouterr().out


def test_loader_uses_private_captured_pipes_and_relative_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "path with spaces"
    directory.mkdir()
    destination = directory / ".env"
    destination.write_text("SYNTHETIC_KEY=not-printed\n")
    destination.chmod(0o600)
    monkeypatch.setenv(local_start.SETUP_TOKEN_ENV, "stale-owner-token")
    parse = Mock(
        return_value=Mock(
            returncode=0, stdout=json.dumps({"SYNTHETIC_KEY": "not-printed"}), stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", parse)
    assert local_start.load_environment(destination, tmp_path, "uv") == {
        "SYNTHETIC_KEY": "not-printed"
    }
    arguments = parse.call_args.args[0]
    assert arguments[arguments.index("--env-file") + 1] == "./.env"
    assert parse.call_args.kwargs["cwd"] == directory
    assert parse.call_args.kwargs["capture_output"] is True
    assert "shell" not in parse.call_args.kwargs
    assert local_start.SETUP_TOKEN_ENV not in parse.call_args.kwargs["env"]


def test_worker_command_drops_inherited_and_settings_file_owner_tokens(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = synthetic_root / ".env"
    destination.write_text("SYNTHETIC_SETTING=fixture\n")
    destination.chmod(0o600)
    monkeypatch.setenv(local_start.SETUP_TOKEN_ENV, "stale-inherited-token")
    monkeypatch.setattr(
        local_start,
        "load_environment",
        Mock(return_value={local_start.SETUP_TOKEN_ENV: "stale-dotenv-token"}),
    )

    def launch(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert local_start.SETUP_TOKEN_ENV not in os.environ
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(subprocess, "run", launch)
    assert local_start.main(["--command", "worker"]) == 0


def test_loader_rejects_unsupported_basename_whitespace_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "settings file.env"
    destination.write_text("SYNTHETIC_KEY=not-printed\n")
    destination.chmod(0o600)
    parse = Mock()
    monkeypatch.setattr(subprocess, "run", parse)
    with pytest.raises(ValueError, match="filename containing whitespace"):
        local_start.load_environment(destination, tmp_path, "uv")
    parse.assert_not_called()


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_backup_operations_require_stopped_writes_before_loading_any_settings(
    synthetic_root: Path, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    load = Mock()
    monkeypatch.setattr(local_start, "load_environment", load)
    with pytest.raises(SystemExit) as stopped:
        local_start.main(["--command", operation, "--output", str(synthetic_root / "new-output")])
    assert stopped.value.code == 2
    load.assert_not_called()


def test_restore_requires_current_ledger_before_loading_any_settings(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    load = Mock()
    monkeypatch.setattr(local_start, "load_environment", load)
    with pytest.raises(SystemExit) as stopped:
        local_start.main(
            [
                "--command",
                "restore",
                "--output",
                str(synthetic_root / "new-output"),
                "--input",
                str(synthetic_root / "archive.enc"),
                "--writes-stopped",
            ]
        )
    assert stopped.value.code == 2
    load.assert_not_called()
