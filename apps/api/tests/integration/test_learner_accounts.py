"""Account identity, reset races, authorization, and private credential boundaries."""

from typing import Any
from uuid import UUID

import pytest
from httpx2 import AsyncClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_workflows import adult as adult
from test_workflows import anyio_backend as anyio_backend
from test_workflows import client
from test_workflows import engine as engine

from math_tutor import auth
from math_tutor.adapters.db.models import Learner

PASSWORD = "synthetic-learner-password"
REPLACEMENT = "synthetic-replacement-password"


async def create(adult: AsyncClient, name: str = "River") -> dict[str, Any]:
    response = await adult.post(
        "/api/v1/admin/learners", json={"alias": name, "password": PASSWORD, "eligibility": "minor"}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def login(browser: AsyncClient, name: str, password: str) -> Any:
    browser.headers["X-CSRF-Token"] = (await browser.get("/api/v1/auth/session")).json()[
        "csrf_token"
    ]
    response = await browser.post(
        "/api/v1/auth/login", json={"login_name": name, "password": password}
    )
    if response.status_code == 200:
        browser.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


@pytest.mark.anyio
async def test_unique_normalized_names_include_admin_and_unicode(
    adult: AsyncClient, engine: Engine
) -> None:
    row = await create(adult, "  River   Blue  ")
    assert row["alias"] == "River Blue" and row["has_password"]
    for duplicate in ["river blue", "Ｒｉｖｅｒ　Ｂｌｕｅ", "DEMO"]:
        response = await adult.post(
            "/api/v1/admin/learners", json={"alias": duplicate, "password": PASSWORD}
        )
        assert response.status_code == 409
    with Session(engine) as db:
        db.add(Learner(alias="RIVER BLUE"))
        with pytest.raises(IntegrityError):
            db.flush()
    with Session(engine) as db, pytest.raises(ValueError, match="administrator already exists"):
        auth.create_or_reset_admin(db, "another-admin", PASSWORD)


@pytest.mark.anyio
async def test_password_is_write_only_and_reset_revokes_sign_ins(
    adult: AsyncClient, engine: Engine
) -> None:
    row = await create(adult)
    with Session(engine) as db:
        stored = db.get(Learner, UUID(row["id"]))
        assert stored and stored.password_hash and stored.password_hash != PASSWORD
        assert auth.verify_password(stored.password_hash, PASSWORD)
    for path in ["/api/v1/admin/learners", f"/api/v1/admin/learners/{row['id']}/export"]:
        response = await (adult.get(path) if path.endswith("learners") else adult.post(path))
        assert "password_hash" not in response.text and PASSWORD not in response.text
    async with client(engine) as browser:
        assert (await login(browser, "river", "wrong-password")).status_code == 401
        signed = await login(browser, " RIVER ", PASSWORD)
        assert signed.status_code == 200
        assert signed.json()["role"] == "learner" and signed.json()["learner_id"] == row["id"]
        assert (await browser.get("/api/v1/admin/learners")).status_code == 403
        assert (
            await browser.patch(
                f"/api/v1/admin/learners/{row['id']}/account",
                json={"alias": "River", "password": REPLACEMENT},
            )
        ).status_code == 403
        devices = (await adult.get(f"/api/v1/admin/learners/{row['id']}/devices")).json()
        assert len(devices) == 1 and set(devices[0]) == {"id", "created_at", "expires_at"}
        reset = await adult.patch(
            f"/api/v1/admin/learners/{row['id']}/account",
            json={"alias": "River", "password": REPLACEMENT},
        )
        assert reset.status_code == 200
        assert (await browser.get("/api/v1/auth/session")).json()["authenticated"] is False
        assert (await login(browser, "River", PASSWORD)).status_code == 401
        assert (await login(browser, "River", REPLACEMENT)).status_code == 200
        own = (await adult.get(f"/api/v1/admin/learners/{row['id']}/devices")).json()[0]
        other = await create(adult, "Sky")
        assert (
            await adult.delete(f"/api/v1/admin/learners/{other['id']}/devices/{own['id']}")
        ).status_code == 404
        assert (
            await adult.delete(f"/api/v1/admin/learners/{row['id']}/devices/{own['id']}")
        ).status_code == 200
        assert (await browser.get("/api/v1/sessions")).status_code == 401


@pytest.mark.anyio
async def test_reset_during_password_verification_prevents_stale_login(
    adult: AsyncClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = await create(adult)
    authenticate = auth.authenticate_learner

    def verify_then_reset(db: Session, name: str, password: str) -> Learner | None:
        result = authenticate(db, name, password)
        with Session(engine) as writer:
            learner = writer.get(Learner, UUID(row["id"]))
            assert learner
            learner.password_hash = auth.hash_password(REPLACEMENT)
            writer.commit()
        return result

    monkeypatch.setattr(auth, "authenticate_learner", verify_then_reset)
    async with client(engine) as browser:
        assert (await login(browser, "River", PASSWORD)).status_code == 401
        assert (await browser.get("/api/v1/auth/session")).json()["authenticated"] is False


@pytest.mark.anyio
async def test_existing_profile_requires_explicit_password_and_rename_keeps_identity(
    adult: AsyncClient, engine: Engine
) -> None:
    with Session(engine) as db:
        learner = Learner(alias="Prior profile")
        db.add(learner)
        db.commit()
        identifier = str(learner.id)
    rows = (await adult.get("/api/v1/admin/learners")).json()
    assert next(row for row in rows if row["id"] == identifier)["has_password"] is False
    async with client(engine) as browser:
        assert (await login(browser, "Prior profile", PASSWORD)).status_code == 401
        response = await adult.patch(
            f"/api/v1/admin/learners/{identifier}/account",
            json={"alias": "Renamed profile", "password": PASSWORD},
        )
        assert response.status_code == 200 and response.json()["id"] == identifier
        assert (await login(browser, "Prior profile", PASSWORD)).status_code == 401
        assert (await login(browser, "Renamed profile", PASSWORD)).json()[
            "learner_id"
        ] == identifier
