"""Renew Docker setup against a real socket, real SQLite and the browser API."""

import socket
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_browser_setup import EXCHANGE, SETUP, body, client, csrf
from test_browser_setup import anyio_backend as anyio_backend
from test_browser_setup import app as app
from test_browser_setup import db_url as db_url
from test_browser_setup import engine as engine
from test_browser_setup import private_environment as private_environment

from math_tutor import owner_setup
from math_tutor.adapters.db.models import Administrator
from math_tutor.setup_gate import SetupGate


def request_link(path: Path) -> str:
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(str(path))
        connection.sendall(b"setup-link\n")
        with connection.makefile("rb") as response:
            return response.read(4096).decode()


@pytest.mark.anyio
async def test_container_owner_renews_expired_link_and_cannot_reset_claimed_account(
    app: FastAPI, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "owner/setup.sock"
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(path))
    gate: SetupGate = app.state.setup_gate
    with owner_setup.owner_channel(engine, gate):
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        first = request_link(path).split("#setup=")[1].strip()
        assert gate.accepts(first)
        gate._expires_at = 0  # Reproduce the expired link from a detached container.
        assert not gate.available()
        second = request_link(path).split("#setup=")[1].strip()
        assert second != first and gate.accepts(second) and not gate.accepts(first)
        async with client(app) as browser:
            public = await browser.get(SETUP)
            assert public.json()["available"] is False
            assert first not in public.text and second not in public.text
            await csrf(browser)
            denied = await browser.post(EXCHANGE, json={"setup_token": first})
            assert denied.status_code == 403
            exchanged = await browser.post(EXCHANGE, json={"setup_token": second})
            assert exchanged.status_code == 200
            created = await browser.post(SETUP, json=body())
            assert created.status_code == 200, created.text
            assert created.json()["authenticated"] is True
            assert not gate.available()
            refused = request_link(path)
            assert "Sign in at " in refused and "#setup=" not in refused
        async with client(app) as visitor:
            await csrf(visitor)
            replay = await visitor.post(EXCHANGE, json={"setup_token": second})
            assert replay.status_code == 409
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Administrator)) == 1
    assert not path.exists()


def test_owner_cli_reaches_running_gate_without_logging_link_in_server(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "owner/setup.sock"
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(path))
    gate = SetupGate()
    with owner_setup.owner_channel(engine, gate):
        assert owner_setup.main() == 0
        output = capsys.readouterr()
        assert not output.err and output.out.count("#setup=") == 1
        assert gate.accepts(output.out.split("#setup=")[1].strip())


@pytest.mark.parametrize("permissions", [0o755, 0o770])
def test_owner_channel_rejects_shared_directory(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permissions: int
) -> None:
    directory = tmp_path / "shared"
    directory.mkdir(mode=permissions)
    directory.chmod(permissions)
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(directory / "setup.sock"))
    with (
        pytest.raises(ValueError, match="owner-only directory"),
        owner_setup.owner_channel(engine, SetupGate()),
    ):
        pytest.fail("Shared directory accepted")


def test_owner_channel_does_not_replace_a_live_socket(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "owner/setup.sock"
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(path))
    with owner_setup.owner_channel(engine, SetupGate()):
        with (
            pytest.raises(ValueError, match="already running"),
            owner_setup.owner_channel(engine, SetupGate()),
        ):
            pytest.fail("Live listener replaced")
        assert "#setup=" in request_link(path)


def test_owner_channel_is_disabled_in_demo(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "owner/setup.sock"
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(path))
    monkeypatch.setenv("APP_MODE", "demo")
    gate = SetupGate()
    with owner_setup.owner_channel(engine, gate):
        assert not path.exists()
        assert "unavailable" in owner_setup.owner_response(engine, gate)
        assert not gate.available()


def test_owner_channel_is_wired_to_api_lifespan(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    path = tmp_path / "owner/setup.sock"
    monkeypatch.setenv(owner_setup.SOCKET_ENV, str(path))
    with TestClient(app):
        assert "#setup=" in request_link(path)
    assert not path.exists()
