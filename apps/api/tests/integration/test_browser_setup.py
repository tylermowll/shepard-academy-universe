"""Owner-authorized first account setup against real temporary SQLite files."""

import asyncio
import json
import os
import sqlite3
import time
from threading import Barrier
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_sessions import MIGRATIONS_DIR, TEST_ORIGIN, TEST_SECRET, create_admin
from test_auth_sessions import anyio_backend as anyio_backend
from test_auth_sessions import db_url as db_url
from test_auth_sessions import engine as engine

from math_tutor import auth, settings
from math_tutor.adapters.db.models import Administrator, DeviceSession
from math_tutor.api.app import create_app
from math_tutor.api.auth import ANON_CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from math_tutor.setup_gate import SETUP_TOKEN_ENV_VAR, SetupGate

OWNER_TOKEN = "synthetic-local-owner-token-0123456789abcdef"
NEW_OWNER_TOKEN = "different-synthetic-owner-token-fedcba9876543210"
PASSWORD = "plain6"
NETWORK_PASSWORD = "simplepassword12"
SETUP = "/api/v1/auth/setup"


@pytest.fixture(autouse=True)
def private_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "private")
    monkeypatch.delenv(SETUP_TOKEN_ENV_VAR, raising=False)
    auth.clear_login_rate_limit()


@pytest.fixture
def app(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, OWNER_TOKEN)
    return create_app(engine)


def client(app: FastAPI, origin: str = TEST_ORIGIN) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=origin)


def body(**changes: Any) -> dict[str, Any]:
    return {
        "setup_token": OWNER_TOKEN,
        "login_name": " Owner ",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
        **changes,
    }


async def csrf(browser: AsyncClient) -> str:
    response = await browser.get("/api/v1/auth/session")
    assert response.status_code == 200, response.text
    browser.headers[CSRF_HEADER] = response.json()["csrf_token"]
    return str(response.json()["csrf_token"])


@pytest.mark.anyio
async def test_first_owner_setup_signs_in_and_never_exposes_secrets(
    app: FastAPI, engine: Engine
) -> None:
    assert SETUP_TOKEN_ENV_VAR not in os.environ
    assert OWNER_TOKEN not in repr(app.state.setup_gate)
    assert app.state.setup_gate._token_hash == auth.hash_opaque_token(OWNER_TOKEN)
    async with client(app) as browser:
        status = await browser.get(SETUP)
        assert status.json() == {
            "required": True,
            "available": True,
            "minimum_password_length": 6,
            "maximum_password_length": 256,
            "local_passwords_allowed": True,
        }
        assert status.headers["Cache-Control"] == "no-store"
        initial = await browser.get("/api/v1/auth/session")
        assert initial.json()["setup_required"] is True
        browser.headers[CSRF_HEADER] = initial.json()["csrf_token"]
        response = await browser.post(SETUP, json=body())
        assert response.status_code == 200, response.text
        assert response.json() == {
            "authenticated": True,
            "role": "adult",
            "login_name": "Owner",
            "csrf_token": response.json()["csrf_token"],
        }
        assert response.cookies.get(SESSION_COOKIE)
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
        assert "Secure" not in response.headers["set-cookie"]
        assert not browser.cookies.get(ANON_CSRF_COOKIE)
        assert OWNER_TOKEN not in response.text and PASSWORD not in response.text
        assert (await browser.get("/api/v1/auth/session")).json()["authenticated"]
        assert (await browser.get("/api/v1/admin/learners")).status_code == 200
        claimed = (await browser.get(SETUP)).json()
        assert not claimed["required"] and not claimed["available"]
    assert not app.state.setup_gate.available()
    with Session(engine) as db:
        admin = db.scalar(select(Administrator))
        assert admin is not None and admin.login_name == "Owner" and admin.local_only_password
        assert admin.password_hash.startswith("$argon2id$") and PASSWORD not in admin.password_hash
        assert auth.verify_password(admin.password_hash, PASSWORD)
        assert db.scalar(select(func.count()).select_from(DeviceSession)) == 1


@pytest.mark.anyio
async def test_setup_status_does_not_issue_authority_without_launcher_token(engine: Engine) -> None:
    app = create_app(engine)
    async with client(app) as browser:
        status = (await browser.get(SETUP)).json()
        assert status["required"] and not status["available"]
        assert "token" not in str(status)
        await csrf(browser)
        result = await browser.post(SETUP, json=body())
        assert result.status_code == 403 and result.json()["code"] == "setup_unavailable"
    with Session(engine) as db:
        assert db.scalar(select(Administrator.id)) is None


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["wrong_token", "expired", "csrf", "origin", "host"])
async def test_setup_rejects_invalid_authority_origin_csrf_without_creating_account(
    app: FastAPI, engine: Engine, failure: str
) -> None:
    async with client(app) as browser:
        await csrf(browser)
        payload = body()
        if failure == "wrong_token":
            payload["setup_token"] = NEW_OWNER_TOKEN
        elif failure == "expired":
            app.state.setup_gate._expires_at = time.monotonic() - 1
        elif failure == "csrf":
            browser.headers[CSRF_HEADER] = "wrong"
        elif failure == "origin":
            browser.headers["Origin"] = "https://attacker.invalid"
        else:
            browser.headers["Host"] = "attacker.invalid"
            browser.headers["X-Forwarded-Host"] = "127.0.0.1:8000"
        response = await browser.post(SETUP, json=payload)
        assert response.status_code == 403
        assert OWNER_TOKEN not in response.text and NEW_OWNER_TOKEN not in response.text
        if failure in {"wrong_token", "expired"}:
            assert response.json()["code"] == "setup_link_invalid"
    with Session(engine) as db:
        assert db.scalar(select(Administrator.id)) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad_password", ["short", "      ", "abcdef\n", "abcdef\x00", "abcdef\ud800", "x" * 257]
)
async def test_invalid_passwords_remain_recoverable_inline(
    app: FastAPI, engine: Engine, bad_password: str
) -> None:
    async with client(app) as browser:
        await csrf(browser)
        response = await browser.post(
            SETUP,
            content=json.dumps(body(password=bad_password, password_confirmation=bad_password)),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert OWNER_TOKEN not in response.text and bad_password not in response.text
        assert app.state.setup_gate.available()
        assert (await browser.post(SETUP, json=body())).status_code == 200


@pytest.mark.anyio
async def test_password_mismatch_and_invalid_name_are_safe_and_recoverable(app: FastAPI) -> None:
    async with client(app) as browser:
        await csrf(browser)
        mismatch = await browser.post(SETUP, json=body(password_confirmation="different"))
        assert mismatch.status_code == 422 and mismatch.json()["code"] == "password_mismatch"
        for name in (" ", "bad\nname", "bad\x00name"):
            response = await browser.post(SETUP, json=body(login_name=name))
            assert response.status_code == 422 and response.json()["code"] == "invalid_credentials"
        assert app.state.setup_gate.available()
        assert (await browser.post(SETUP, json=body())).status_code == 200


@pytest.mark.anyio
async def test_first_claim_is_atomic_and_replay_cannot_add_or_reset(
    app: FastAPI, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = Barrier(2)
    original_hash = auth.hash_password

    def together(password: str) -> str:
        result = original_hash(password)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(auth, "hash_password", together)
    async with client(app) as first, client(app) as second:
        await csrf(first)
        await csrf(second)
        responses = await asyncio.gather(
            first.post(SETUP, json=body(login_name="first")),
            second.post(SETUP, json=body(login_name="second")),
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        losing = next(r for r in responses if r.status_code == 409)
        assert losing.json()["code"] == "setup_claimed"
        winner_name = next(r.json()["login_name"] for r in responses if r.status_code == 200)
        async with client(app) as replay:
            await csrf(replay)
            response = await replay.post(
                SETUP,
                json=body(
                    login_name=winner_name,
                    password=NETWORK_PASSWORD,
                    password_confirmation=NETWORK_PASSWORD,
                ),
            )
            assert response.status_code == 409 and response.json()["code"] == "setup_claimed"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Administrator)) == 1
        assert db.scalar(select(func.count()).select_from(DeviceSession)) == 1
        admin = db.scalar(select(Administrator))
        assert admin is not None and auth.verify_password(admin.password_hash, PASSWORD)


@pytest.mark.anyio
async def test_transaction_failure_keeps_setup_authority_for_retry(
    app: FastAPI, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_create = auth.create_device_session

    def fail(_db: Session, _admin: Administrator) -> tuple[DeviceSession, str]:
        raise OperationalError(
            "synthetic session insert", {}, sqlite3.OperationalError("synthetic disk failure")
        )

    async with client(app) as browser:
        await csrf(browser)
        monkeypatch.setattr(auth, "create_device_session", fail)
        failed = await browser.post(SETUP, json=body())
        assert failed.status_code == 503
        assert OWNER_TOKEN not in failed.text and PASSWORD not in failed.text
        with Session(engine) as db:
            assert db.scalar(select(Administrator.id)) is None
            assert db.scalar(select(DeviceSession.id)) is None
        assert app.state.setup_gate.available()
        monkeypatch.setattr(auth, "create_device_session", original_create)
        assert (await browser.post(SETUP, json=body())).status_code == 200


@pytest.mark.anyio
async def test_demo_and_existing_accounts_cannot_be_claimed(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, OWNER_TOKEN)
    app = create_app(engine)
    assert SETUP_TOKEN_ENV_VAR not in os.environ and not app.state.setup_gate.available()
    async with client(app) as browser:
        await csrf(browser)
        status = (await browser.get(SETUP)).json()
        assert not status["required"] and not status["available"]
        response = await browser.post(SETUP, json=body())
        assert response.status_code == 403 and response.json()["code"] == "setup_unavailable"
    monkeypatch.setenv("APP_MODE", "private")
    existing = create_admin(engine)
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, OWNER_TOKEN)
    claimed_app = create_app(engine)
    async with client(claimed_app) as browser:
        await csrf(browser)
        response = await browser.post(SETUP, json=body())
        assert response.status_code == 409
    with Session(engine) as db:
        rows = list(db.scalars(select(Administrator)))
        assert len(rows) == 1 and rows[0].id == existing.id
        assert rows[0].password_hash == existing.password_hash


@pytest.mark.anyio
async def test_setup_rate_limit_is_bounded_and_returns_retry_after(app: FastAPI) -> None:
    async with client(app) as browser:
        await csrf(browser)
        for _ in range(auth.LOGIN_RATE_LIMIT):
            assert (
                await browser.post(SETUP, json=body(setup_token=NEW_OWNER_TOKEN))
            ).status_code == 403
        response = await browser.post(SETUP, json=body())
        assert response.status_code == 429 and response.json()["code"] == "setup_rate_limited"
        assert 1 <= int(response.headers["Retry-After"]) <= 60
        assert app.state.setup_gate.available()


@pytest.mark.anyio
async def test_network_setup_requires_twelve_and_ignores_forwarded_local_headers(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = "https://tutor.example"
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, origin)
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, OWNER_TOKEN)
    app = create_app(engine)
    async with client(app, origin) as browser:
        status = (await browser.get(SETUP)).json()
        assert status["minimum_password_length"] == 12 and not status["local_passwords_allowed"]
        await csrf(browser)
        response = await browser.post(
            SETUP,
            json=body(),
            headers={"X-Forwarded-Host": "localhost", "X-Forwarded-Proto": "http"},
        )
        assert response.status_code == 422
        accepted = await browser.post(
            SETUP, json=body(password=NETWORK_PASSWORD, password_confirmation=NETWORK_PASSWORD)
        )
        assert accepted.status_code == 200 and "Secure" in accepted.headers["set-cookie"]
    with Session(engine) as db:
        admin = db.scalar(select(Administrator))
        assert admin is not None and not admin.local_only_password


@pytest.mark.anyio
async def test_local_only_password_and_existing_session_are_blocked_on_https_until_reset(
    app: FastAPI, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with client(app) as browser:
        await csrf(browser)
        response = await browser.post(SETUP, json=body())
        assert response.status_code == 200
        old_session = browser.cookies[SESSION_COOKIE]
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "https://127.0.0.1:8000")
    async with client(app, "https://127.0.0.1:8000") as browser:
        browser.cookies.set(SESSION_COOKIE, old_session)
        assert (await browser.get("/api/v1/auth/session")).json()["authenticated"] is False
        assert (await browser.get("/api/v1/admin/learners")).status_code == 401
        await csrf(browser)
        wrong = await browser.post(
            "/api/v1/auth/login", json={"login_name": "Owner", "password": "wrong"}
        )
        assert wrong.status_code == 401 and "local-only" not in wrong.text
        blocked = await browser.post(
            "/api/v1/auth/login", json={"login_name": "Owner", "password": PASSWORD}
        )
        assert blocked.status_code == 403 and "make admin" in blocked.text
        with Session(engine) as db:
            admin = auth.create_or_reset_admin(db, "Owner", NETWORK_PASSWORD)
            assert not admin.local_only_password
            db.commit()
        accepted = await browser.post(
            "/api/v1/auth/login", json={"login_name": "Owner", "password": NETWORK_PASSWORD}
        )
        assert accepted.status_code == 200
    with Session(engine) as db:
        assert auth.get_valid_session(db, old_session) is None


def test_local_password_migration_preserves_existing_accounts_and_refuses_unsafe_downgrade(
    engine: Engine, db_url: str
) -> None:
    configuration = Config()
    configuration.set_main_option("script_location", str(MIGRATIONS_DIR))
    configuration.set_main_option("sqlalchemy.url", db_url)
    # A successful rollback/re-upgrade preserves existing strong accounts.
    existing = create_admin(engine)
    command.downgrade(configuration, "0012_provider_connections")
    assert "local_only_password" not in {
        column["name"] for column in inspect(engine).get_columns("administrator")
    }
    command.upgrade(configuration, "head")
    with Session(engine) as db:
        restored = db.get(Administrator, existing.id)
        assert restored is not None and not restored.local_only_password
        assert restored.password_hash == existing.password_hash
        auth.create_or_reset_admin(db, existing.login_name, PASSWORD)
        db.commit()
    with pytest.raises(RuntimeError, match="at least 12"):
        command.downgrade(configuration, "0012_provider_connections")
    with Session(engine) as db:
        admin = db.get(Administrator, existing.id)
        assert admin is not None and admin.local_only_password
        assert auth.verify_password(admin.password_hash, PASSWORD)
        assert (
            db.connection().exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == "0016_reasoning_effort"
        )


def test_gate_restarts_replace_authority_and_retains_only_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, TEST_SECRET)
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, OWNER_TOKEN)
    first = SetupGate.from_environment()
    assert first.accepts(OWNER_TOKEN)
    assert SETUP_TOKEN_ENV_VAR not in os.environ and OWNER_TOKEN not in repr(first)
    assert not SetupGate.from_environment().available()
    monkeypatch.setenv(SETUP_TOKEN_ENV_VAR, NEW_OWNER_TOKEN)
    restarted = SetupGate.from_environment()
    assert restarted.accepts(NEW_OWNER_TOKEN) and not restarted.accepts(OWNER_TOKEN)
    restarted.consume()
    assert not restarted.available() and not restarted.accepts(NEW_OWNER_TOKEN)


@pytest.mark.anyio
async def test_malformed_unicode_setup_and_login_inputs_fail_safely(app: FastAPI) -> None:
    async with client(app) as browser:
        await csrf(browser)
        for change, expected in (
            ({"setup_token": "\ud800"}, 403),
            ({"password_confirmation": "\ud800"}, 422),
            ({"login_name": "name\ud800"}, 422),
        ):
            response = await browser.post(
                SETUP,
                content=json.dumps(body(**change)),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == expected
            assert OWNER_TOKEN not in response.text
        assert (await browser.post(SETUP, json=body())).status_code == 200
        await browser.post(
            "/api/v1/auth/logout",
            headers={CSRF_HEADER: (await browser.get("/api/v1/auth/session")).json()["csrf_token"]},
        )
        await csrf(browser)
        for login, password in (("Owner", "\ud800"), ("\ud800", PASSWORD)):
            response = await browser.post(
                "/api/v1/auth/login",
                content=json.dumps({"login_name": login, "password": password}),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 422
            assert response.json() == {"detail": "Invalid request."}
