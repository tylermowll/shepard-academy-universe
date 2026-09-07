"""On-disk authentication gates for T02.

Adult bootstrap/login, opaque sessions, CSRF, expiry, revocation, and rate
limits run against isolated temporary databases with the production
connection settings and generated synthetic secrets. No operator database,
live secret, or real credential is touched.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from math_tutor import auth as auth_service
from math_tutor import cli, settings
from math_tutor.adapters.db.engine import create_engine_for_url
from math_tutor.adapters.db.models import Administrator, DeviceSession
from math_tutor.api.app import create_app
from math_tutor.api.auth import ANON_CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
HEAD_REVISION = "0002_auth_sessions"

TEST_SECRET = "t02-synthetic-session-secret-0123456789abcdef"
TEST_ORIGIN = "http://test"
ADMIN_LOGIN = "grownup"
ADMIN_PASSWORD = "correct-horse-battery-99"


@pytest.fixture
def anyio_backend() -> str:
    """Keep these API tests on the standard-library asyncio backend."""

    return "asyncio"


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point settings at an isolated temporary database and synthetic secret."""

    url = f"sqlite+pysqlite:///{tmp_path / 'auth.sqlite3'}"
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, url)
    monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, TEST_SECRET)
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, TEST_ORIGIN)
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    """Migrated engine with the production connection settings for one test."""

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
    eng = create_engine_for_url(db_url)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(autouse=True)
def _clean_rate_limit() -> Iterator[None]:
    auth_service.clear_login_rate_limit()
    try:
        yield
    finally:
        auth_service.clear_login_rate_limit()


def make_client(engine: Engine, base_url: str = TEST_ORIGIN) -> AsyncClient:
    """Build an API client bound to the test database."""

    transport = ASGITransport(app=create_app(engine))
    return AsyncClient(transport=transport, base_url=base_url)


def create_admin(
    engine: Engine, login: str = ADMIN_LOGIN, password: str = ADMIN_PASSWORD
) -> Administrator:
    """Persist an administrator row with a real Argon2id hash."""

    with Session(engine) as db:
        admin = auth_service.create_or_reset_admin(db, login, password)
        db.commit()
        db.refresh(admin)
        db.expunge(admin)
        return admin


async def bootstrap_csrf(client: AsyncClient) -> str:
    """Fetch the anonymous bootstrap token (sets the anon cookie)."""

    response = await client.get("/api/v1/auth/session")
    assert response.status_code == 200
    body = response.json()
    assert body == {"authenticated": False, "csrf_token": body["csrf_token"]}
    assert response.cookies.get(ANON_CSRF_COOKIE) == body["csrf_token"]
    return str(body["csrf_token"])


async def attempt_login(
    client: AsyncClient,
    login: str = ADMIN_LOGIN,
    password: str = ADMIN_PASSWORD,
    csrf: str | None = None,
    origin: str | None = None,
) -> Response:
    """POST a login, bootstrapping CSRF unless an explicit token is given."""

    token = csrf if csrf is not None else await bootstrap_csrf(client)
    headers = {CSRF_HEADER: token}
    if origin is not None:
        headers["Origin"] = origin
    return await client.post(
        "/api/v1/auth/login",
        json={"login_name": login, "password": password},
        headers=headers,
    )


async def login_ok(client: AsyncClient) -> str:
    """Log in and return the authenticated session's CSRF token."""

    response = await attempt_login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["role"] == "adult"
    assert body["login_name"] == ADMIN_LOGIN
    return str(body["csrf_token"])


def test_auth_tables_migrate_from_empty_file(engine: Engine) -> None:
    with engine.connect() as connection:
        names = inspect(connection).get_table_names()
        assert {
            "practice_session",
            "problem_instance",
            "administrator",
            "device_session",
            "alembic_version",
        } == set(names)
        admin_columns = {
            column["name"] for column in inspect(connection).get_columns("administrator")
        }
        session_columns = {
            column["name"] for column in inspect(connection).get_columns("device_session")
        }
        admin_uniques = inspect(connection).get_unique_constraints("administrator")
        session_uniques = inspect(connection).get_unique_constraints("device_session")
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert version == HEAD_REVISION
    assert admin_columns >= {"id", "login_name", "password_hash", "created_at", "updated_at"}
    assert session_columns >= {
        "id",
        "token_hash",
        "role",
        "administrator_id",
        "learner_id",
        "csrf_token",
        "created_at",
        "expires_at",
        "revoked_at",
    }
    assert {constraint["name"] for constraint in admin_uniques} == {"uq_administrator_login_name"}
    assert {constraint["name"] for constraint in session_uniques} == {
        "uq_device_session_token_hash"
    }


def test_admin_login_names_stay_unique(engine: Engine) -> None:
    create_admin(engine)
    with Session(engine) as db:
        db.add(
            Administrator(
                login_name=ADMIN_LOGIN,
                password_hash=auth_service.hash_password("another-long-password-1"),
                created_at=auth_service.utcnow(),
                updated_at=auth_service.utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_admin_password_policy_and_reset(engine: Engine) -> None:
    with Session(engine) as db:
        with pytest.raises(ValueError, match="at least"):
            auth_service.create_or_reset_admin(db, ADMIN_LOGIN, "short")
        with pytest.raises(ValueError, match="1-64"):
            auth_service.create_or_reset_admin(db, "   ", ADMIN_PASSWORD * 4)

    create_admin(engine)
    with Session(engine) as db:
        admin = auth_service.authenticate_admin(db, ADMIN_LOGIN, ADMIN_PASSWORD)
        assert admin is not None
        assert admin.password_hash != ADMIN_PASSWORD
        assert auth_service.authenticate_admin(db, ADMIN_LOGIN, "wrong-password") is None
        assert auth_service.authenticate_admin(db, " stranger ", "whatever") is None

    create_admin(engine, password="a-brand-new-long-password-2")
    with Session(engine) as db:
        assert auth_service.authenticate_admin(db, ADMIN_LOGIN, ADMIN_PASSWORD) is None
        assert (
            auth_service.authenticate_admin(db, ADMIN_LOGIN, "a-brand-new-long-password-2")
            is not None
        )


@pytest.mark.anyio
async def test_auth_rejects_placeholder_secret(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with make_client(engine) as client:
        assert (await client.get("/api/v1/auth/session")).status_code == 200

    for bad in ("GENERATE_AT_SETUP", "short"):
        monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, bad)
        async with make_client(engine) as client:
            missing = await client.get("/api/v1/auth/session")
            assert missing.status_code == 500
            assert missing.json() == {"detail": "Server authentication is not configured."}


@pytest.mark.anyio
async def test_login_sets_session_cookie_and_status(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        response = await attempt_login(client)
        assert response.status_code == 200
        set_cookies = " | ".join(response.headers.get_list("set-cookie"))
        assert f"{SESSION_COOKIE}=" in set_cookies
        assert "HttpOnly" in set_cookies
        assert "SameSite=lax" in set_cookies
        assert "Secure" not in set_cookies  # plain-HTTP test origin
        assert f"{ANON_CSRF_COOKIE}=" in set_cookies  # bootstrap cookie cleared
        assert response.cookies.get(SESSION_COOKIE)

        status_response = await client.get("/api/v1/auth/session")
        assert status_response.status_code == 200
        assert status_response.json() == {
            "authenticated": True,
            "role": "adult",
            "login_name": ADMIN_LOGIN,
            "csrf_token": response.json()["csrf_token"],
        }


@pytest.mark.anyio
async def test_login_responses_never_leak_private_material(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        login_body = (await attempt_login(client)).json()
        assert set(login_body) == {"authenticated", "role", "login_name", "csrf_token"}

        fresh = await client.get("/api/v1/auth/session")
        assert set(fresh.json()) == {"authenticated", "role", "login_name", "csrf_token"}
        for body in (login_body, fresh.json()):
            assert "password_hash" not in body
            assert "token_hash" not in body


@pytest.mark.anyio
async def test_bad_logins_share_one_401_without_session(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        wrong = await attempt_login(client, password="wrong-password-0123456789")
        assert wrong.status_code == 401
        assert wrong.json() == {"detail": "Invalid login name or password."}
        assert wrong.cookies.get(SESSION_COOKIE) is None

        unknown = await attempt_login(client, login="stranger", password="whatever-123456")
        assert unknown.status_code == 401
        assert unknown.json() == wrong.json()
        assert unknown.cookies.get(SESSION_COOKIE) is None


@pytest.mark.anyio
async def test_login_requires_csrf_double_submit(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        csrf = await bootstrap_csrf(client)

        missing = await client.post(
            "/api/v1/auth/login",
            json={"login_name": ADMIN_LOGIN, "password": ADMIN_PASSWORD},
        )
        assert missing.status_code == 403

        forged = await attempt_login(client, csrf="forged-token")
        assert forged.status_code == 403

        swapped = await attempt_login(
            client, csrf=auth_service.sign_anon_csrf("attacker-nonce", TEST_SECRET)
        )
        assert swapped.status_code == 403  # valid signature, wrong browser binding

        assert csrf  # bootstrap token itself remains usable below
        assert (await attempt_login(client, csrf=csrf)).status_code == 200


@pytest.mark.anyio
async def test_login_rejects_mismatched_origin(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        rejected = await attempt_login(client, origin="https://evil.example")
        assert rejected.status_code == 403
        assert rejected.json() == {"detail": "Origin not allowed."}

        allowed = await attempt_login(client, origin=TEST_ORIGIN)
        assert allowed.status_code == 200


@pytest.mark.anyio
async def test_logout_requires_session_csrf_and_revokes(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        csrf = await login_ok(client)

        assert (await client.post("/api/v1/auth/logout")).status_code == 403
        forged = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: "wrong"})
        assert forged.status_code == 403

        done = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: csrf})
        assert done.status_code == 200
        assert done.json() == {"authenticated": False}
        assert "Max-Age=0" in " | ".join(done.headers.get_list("set-cookie"))

        assert (await client.get("/api/v1/auth/session")).json()["authenticated"] is False
        replay = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: csrf})
        assert replay.status_code == 401

    with Session(engine) as db:
        row = db.scalar(select(DeviceSession))
        assert row is not None
        assert row.revoked_at is not None


@pytest.mark.anyio
async def test_logout_revokes_only_the_presenting_session(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as first:
        first_csrf = await login_ok(first)
        async with make_client(engine) as second:
            await login_ok(second)

            assert (
                await first.post("/api/v1/auth/logout", headers={CSRF_HEADER: first_csrf})
            ).status_code == 200
            still_valid = await second.get("/api/v1/auth/session")
            assert still_valid.json()["authenticated"] is True


@pytest.mark.anyio
async def test_expired_and_tampered_sessions_are_rejected(engine: Engine) -> None:
    admin = create_admin(engine)
    with Session(engine) as db:
        row, token = auth_service.create_device_session(db, db.merge(admin))
        row.expires_at = auth_service.utcnow() - timedelta(seconds=1)
        csrf = row.csrf_token
        db.commit()

    async with make_client(engine) as client:
        client.cookies.set(SESSION_COOKIE, token)
        assert (await client.get("/api/v1/auth/session")).json()["authenticated"] is False
        expired_logout = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: csrf})
        assert expired_logout.status_code == 401

    async with make_client(engine) as client:
        client.cookies.set(SESSION_COOKIE, auth_service.new_opaque_token())
        assert (await client.get("/api/v1/auth/session")).json()["authenticated"] is False


@pytest.mark.anyio
async def test_secure_cookie_flag_follows_https_origin(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_admin(engine)
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "https://tutor.example")
    # Secure cookies are only returned over https, matching browser behavior.
    async with make_client(engine, base_url="https://tutor.example") as client:
        response = await attempt_login(client)
        assert response.status_code == 200
        assert "Secure" in " | ".join(response.headers.get_list("set-cookie"))


@pytest.mark.anyio
async def test_login_rate_limit_returns_retry_after(engine: Engine) -> None:
    create_admin(engine)
    async with make_client(engine) as client:
        csrf = await bootstrap_csrf(client)
        statuses: list[int] = []
        for _ in range(auth_service.LOGIN_RATE_LIMIT + 1):
            attempt = await attempt_login(client, login="stranger", csrf=csrf)
            statuses.append(attempt.status_code)
        assert statuses[:-1] == [401] * auth_service.LOGIN_RATE_LIMIT
        assert statuses[-1] == 429
        assert attempt.headers.get("retry-after") is not None


def test_cli_admin_creates_and_reports(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["grownup", "correct-horse-battery-99", "correct-horse-battery-99"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(
        "getpass.getpass",
        lambda _: next(answers),  # noqa: ARG005
    )

    assert cli.main(["admin"]) == 0
    assert "Administrator 'grownup' is ready." in capsys.readouterr().out

    with Session(engine) as db:
        stored = db.scalar(select(Administrator).where(Administrator.login_name == "grownup"))
        assert stored is not None
        assert stored.password_hash != ADMIN_PASSWORD
        assert auth_service.verify_password(stored.password_hash, ADMIN_PASSWORD) is True


def test_cli_admin_rejects_mismatch_and_short_password(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "grownup")
    mismatch = iter(["first-long-password-1", "second-long-password-2"])
    monkeypatch.setattr("getpass.getpass", lambda _: next(mismatch))

    assert cli.main(["admin"]) == 1
    assert "do not match" in capsys.readouterr().err

    short = iter(["short", "short"])
    monkeypatch.setattr("getpass.getpass", lambda _: next(short))
    assert cli.main(["admin"]) == 1
    assert "at least" in capsys.readouterr().err

    with Session(engine) as db:
        assert db.scalar(select(Administrator)) is None


def test_cli_admin_rejects_placeholder_secret_before_prompting(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _must_not_prompt(_prompt: str = "") -> Any:
        raise AssertionError("must reject the secret before prompting")

    monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, "GENERATE_AT_SETUP")
    monkeypatch.setattr("builtins.input", _must_not_prompt)
    monkeypatch.setattr("getpass.getpass", _must_not_prompt)

    assert cli.main(["admin"]) == 1
    assert "placeholder" in capsys.readouterr().err


def test_cli_admin_points_at_migrations_when_tables_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    db_url: str,
) -> None:
    assert db_url  # synthetic secret/database settings come from this fixture
    fresh = f"sqlite+pysqlite:///{tmp_path / 'unmigrated.sqlite3'}"
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, fresh)
    monkeypatch.setattr("builtins.input", lambda _: "grownup")
    monkeypatch.setattr("getpass.getpass", lambda _: ADMIN_PASSWORD)

    assert cli.main(["admin"]) == 1
    assert "make migrate" in capsys.readouterr().err
