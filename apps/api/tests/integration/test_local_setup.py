"""First-run/restart against disposable synthetic on-disk state only."""

import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from math_tutor import auth, cli, local_start, settings
from math_tutor.adapters.db.engine import create_engine_for_url
from math_tutor.adapters.db.models import Administrator

ROOT = Path(__file__).resolve().parents[4]
PASSWORD = "synthetic-startup-password-only"


@pytest.fixture
def synthetic_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'private/test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SESSION_SECRET", "synthetic-startup-secret-" * 3)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "http://127.0.0.1:8000")
    return url


def test_first_start_initializes_database_and_creates_only_one_admin(
    synthetic_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_start.prepare_database(ROOT)
    monkeypatch.setattr("builtins.input", lambda _: "synthetic-adult")
    monkeypatch.setattr(getpass, "getpass", lambda _: PASSWORD)
    assert cli.run_admin(only_if_missing=True) == 0
    engine = create_engine_for_url(synthetic_database)
    try:
        with Session(engine) as db:
            admin = db.scalar(select(Administrator))
            assert admin is not None
            identifier, hashed = admin.id, admin.password_hash
            _, token = auth.create_device_session(db, admin)
            db.commit()
        # A routine restart must neither prompt for credentials nor invalidate sessions.
        prompt = Mock(side_effect=AssertionError("A restart cannot reset credentials"))
        migrate = Mock(side_effect=AssertionError("Current databases need no migration"))
        monkeypatch.setattr("builtins.input", prompt)
        monkeypatch.setattr(command, "upgrade", migrate)
        local_start.prepare_database(ROOT)
        assert cli.run_admin(only_if_missing=True) == 0
        prompt.assert_not_called()
        migrate.assert_not_called()
        with Session(engine) as db:
            persisted = db.get(Administrator, identifier)
            assert persisted is not None and persisted.password_hash == hashed
            assert auth.authenticate_admin(db, "synthetic-adult", PASSWORD) is not None
            assert auth.get_valid_session(db, token) is not None
            assert len(db.scalars(select(Administrator)).all()) == 1
    finally:
        engine.dispose()


def test_nonempty_unrecognized_database_is_not_migrated(synthetic_database: str) -> None:
    engine = create_engine_for_url(synthetic_database)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE synthetic_retained (value TEXT NOT NULL)")
            connection.exec_driver_sql("INSERT INTO synthetic_retained VALUES ('keep me')")
        with pytest.raises(ValueError, match="has not migrated or deleted"):
            local_start.prepare_database(ROOT)
        with engine.connect() as connection:
            assert inspect(connection).get_table_names() == ["synthetic_retained"]
            assert (
                connection.exec_driver_sql("SELECT value FROM synthetic_retained").scalar()
                == "keep me"
            )
    finally:
        engine.dispose()


def test_old_schema_requires_explicit_stopped_write_migration(synthetic_database: str) -> None:
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    config.set_main_option("sqlalchemy.url", synthetic_database)
    command.upgrade(config, "0002_auth")
    with pytest.raises(ValueError, match="Stop all API and worker"):
        local_start.prepare_database(ROOT)
    engine = create_engine_for_url(synthetic_database)
    try:
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "0002_auth_sessions"
            )
            assert set(inspect(connection).get_table_names()) == {
                "administrator",
                "alembic_version",
                "device_session",
                "learner",
                "practice_session",
                "problem_instance",
            }
    finally:
        engine.dispose()


def test_admin_created_during_prompt_is_never_reset(
    synthetic_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_start.prepare_database(ROOT)
    engine = create_engine_for_url(synthetic_database)

    def create_while_prompting(_: str) -> str:
        with Session(engine) as db:
            auth.create_or_reset_admin(db, "synthetic-adult", PASSWORD)
            db.commit()
        return "synthetic-adult"

    monkeypatch.setattr("builtins.input", create_while_prompting)
    monkeypatch.setattr(getpass, "getpass", lambda _: "synthetic-different-password-only")
    try:
        assert cli.run_admin(only_if_missing=True) == 0
        with Session(engine) as db:
            assert auth.authenticate_admin(db, "synthetic-adult", PASSWORD) is not None
            assert (
                auth.authenticate_admin(db, "synthetic-adult", "synthetic-different-password-only")
                is None
            )
    finally:
        engine.dispose()


def test_cancelled_first_admin_can_be_retried_without_reinitializing_database(
    synthetic_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_start.prepare_database(ROOT)
    monkeypatch.setattr("builtins.input", Mock(side_effect=EOFError))
    assert cli.run_admin(only_if_missing=True) == 1
    local_start.prepare_database(ROOT)
    monkeypatch.setattr("builtins.input", lambda _: "synthetic-adult")
    monkeypatch.setattr(getpass, "getpass", lambda _: PASSWORD)
    assert cli.run_admin(only_if_missing=True) == 0
    assert settings.database_path().exists()


def test_uv_loads_synthetic_settings_without_shell_evaluation_or_value_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    executable = shutil.which("uv")
    assert executable is not None, "The supported setup toolchain includes uv."
    directory = tmp_path / "directory with spaces"
    directory.mkdir()
    destination = directory / ".env"
    marker = tmp_path / "must-not-exist"
    literal = f"$(touch {marker})"
    destination.write_text(f"T27_SYNTHETIC_LITERAL='{literal}'\n")
    destination.chmod(0o600)
    values = local_start.load_environment(destination, ROOT, executable)
    assert values["T27_SYNTHETIC_LITERAL"] == literal
    assert not marker.exists()
    captured = capsys.readouterr()
    assert literal not in captured.out + captured.err


@pytest.mark.parametrize(
    "contents",
    [
        'SESSION_SECRET="synthetic-t27-secret-value',
        "SESSION_SECRET=synthetic-t27-secret-value\n=malformed",
        "synthetic-t27-secret-value",
    ],
)
def test_malformed_dotenv_is_rejected_without_echoing_secret_lines(
    tmp_path: Path, contents: str, capsys: pytest.CaptureFixture[str]
) -> None:
    executable = shutil.which("uv")
    assert executable is not None
    destination = tmp_path / "synthetic.env"
    destination.write_text(contents)
    destination.chmod(0o600)
    with pytest.raises(ValueError, match="Parser diagnostics were hidden") as failure:
        local_start.load_environment(destination, ROOT, executable)
    captured = capsys.readouterr()
    assert "synthetic-t27-secret-value" not in str(failure.value) + captured.err + captured.out


def test_generated_settings_round_trip_in_directory_with_spaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = shutil.which("uv")
    assert executable is not None
    directory = tmp_path / "household settings"
    directory.mkdir()
    destination = directory / ".env"
    url = f"sqlite+pysqlite:///{directory / 'data/test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_PUBLIC_ORIGIN", "http://127.0.0.1:8000")
    assert cli.run_setup(destination) == 0
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("APP_PUBLIC_ORIGIN")
    values = local_start.load_environment(destination, ROOT, executable)
    assert values["DATABASE_URL"] == url
    assert len(values["SESSION_SECRET"]) >= settings.MIN_SESSION_SECRET_LENGTH
    assert values["APP_PUBLIC_ORIGIN"] == "http://127.0.0.1:8000"


def test_exported_environment_deliberately_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = shutil.which("uv")
    assert executable is not None
    destination = tmp_path / ".env"
    destination.write_text("T27_SYNTHETIC_SETTING=from-file\n")
    destination.chmod(0o600)
    monkeypatch.setenv("T27_SYNTHETIC_SETTING", "explicit-export")
    values = local_start.load_environment(destination, ROOT, executable)
    assert values["T27_SYNTHETIC_SETTING"] == "explicit-export"


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_backup_operations_receive_dotenv_only_database_and_keep_original_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable = shutil.which("uv")
    assert executable is not None
    destination = tmp_path / ".env"
    url = f"sqlite+pysqlite:///{tmp_path / 'configured-only-in-dotenv/test.sqlite3'}"
    destination.write_text(
        f"DATABASE_URL={url}\nSESSION_SECRET=synthetic-backup-settings-secret-value\n"
    )
    destination.chmod(0o600)
    # Isolate environment changes made by the operator dispatcher itself.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SESSION_SECRET", None)
    real_run = subprocess.run
    observed: list[list[str]] = []

    def run(arguments: list[str], **kwargs: Any) -> Any:
        if arguments[:3] == [sys.executable, "-m", "math_tutor.backup"]:
            observed.append(arguments)
            assert kwargs["env"]["DATABASE_URL"] == url
            assert kwargs["env"]["SESSION_SECRET"] == "synthetic-backup-settings-secret-value"
            assert "UV_ENV_FILE" not in kwargs["env"]
            assert "--writes-stopped" in arguments
            return subprocess.CompletedProcess(arguments, 0)
        return real_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    arguments = [
        "--env-file",
        str(destination),
        "--uv",
        executable,
        "--command",
        operation,
        "--output",
        str(tmp_path / "new-output"),
        "--writes-stopped",
    ]
    if operation == "restore":
        arguments.extend(
            [
                "--input",
                str(tmp_path / "archive.enc"),
                "--ledger",
                str(tmp_path / "current-ledger.jsonl"),
            ]
        )
    assert local_start.main(arguments) == 0
    assert len(observed) == 1
    if operation == "backup":
        assert observed[0] == [
            sys.executable,
            "-m",
            "math_tutor.backup",
            "backup",
            str(tmp_path / "new-output"),
            "--writes-stopped",
        ]
    else:
        assert observed[0] == [
            sys.executable,
            "-m",
            "math_tutor.backup",
            "restore",
            str(tmp_path / "archive.enc"),
            "--writes-stopped",
            "--destination",
            str(tmp_path / "new-output"),
            "--deletion-ledger",
            str(tmp_path / "current-ledger.jsonl"),
        ]
    assert not (tmp_path / "new-output").exists()
    assert not settings.database_path().exists()
    captured = capsys.readouterr()
    assert "synthetic-backup-settings-secret-value" not in captured.out + captured.err


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_backup_operations_reject_malformed_settings_without_secret_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable = shutil.which("uv")
    assert executable is not None
    destination = tmp_path / ".env"
    destination.write_text('SESSION_SECRET="synthetic-malformed-backup-secret-value')
    destination.chmod(0o600)
    guard = Mock(
        side_effect=AssertionError("Malformed settings must stop before any storage operation")
    )
    monkeypatch.setattr(local_start, "native_lock", guard)
    arguments = [
        "--env-file",
        str(destination),
        "--uv",
        executable,
        "--command",
        operation,
        "--output",
        str(tmp_path / "new-output"),
        "--writes-stopped",
    ]
    if operation == "restore":
        arguments.extend(
            [
                "--input",
                str(tmp_path / "archive.enc"),
                "--ledger",
                str(tmp_path / "current-ledger.jsonl"),
            ]
        )
    assert local_start.main(arguments) == 1
    guard.assert_not_called()
    captured = capsys.readouterr()
    assert "Parser diagnostics were hidden" in captured.err
    assert "synthetic-malformed-backup-secret-value" not in captured.out + captured.err
