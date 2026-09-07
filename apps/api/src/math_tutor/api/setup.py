"""First-account browser setup requires ephemeral local-owner authority."""

import math
import os
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from math_tutor import auth
from math_tutor.adapters.db.models import Administrator
from math_tutor.api.auth import (
    ANON_CSRF_COOKIE,
    SessionStatus,
    client_key,
    engine_for,
    login_csrf_valid,
    origin_allowed,
    require_secret,
    set_session_cookie,
)
from math_tutor.setup_gate import SetupError, SetupGate

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SetupStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    required: bool
    available: bool
    minimum_password_length: int
    maximum_password_length: int
    local_passwords_allowed: bool


class SetupRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_token: SecretStr = Field(min_length=1, max_length=256, repr=False)
    login_name: str = Field(min_length=1, max_length=auth.MAX_LOGIN_NAME_LENGTH)
    password: SecretStr = Field(min_length=1, max_length=auth.MAX_ADMIN_PASSWORD_LENGTH, repr=False)
    password_confirmation: SecretStr = Field(
        min_length=1, max_length=auth.MAX_ADMIN_PASSWORD_LENGTH, repr=False
    )


def setup_gate(request: Request) -> SetupGate:
    return cast(SetupGate, request.app.state.setup_gate)


@router.get("/setup", response_model=SetupStatus)
def setup_status(request: Request) -> SetupStatus:
    require_secret()
    with Session(engine_for(request)) as db:
        required = auth.setup_required(db)
    return SetupStatus(
        required=required,
        available=required and setup_gate(request).available(),
        minimum_password_length=auth.minimum_admin_password_length(),
        maximum_password_length=auth.MAX_ADMIN_PASSWORD_LENGTH,
        local_passwords_allowed=auth.local_passwords_allowed(),
    )


def require_unclaimed(db: Session) -> None:
    if db.scalar(select(Administrator.id).limit(1)) is not None:
        raise SetupError(
            "setup_claimed",
            "An administrator already exists. Sign in with that account; setup cannot reset it.",
            409,
        )


def require_setup_token(gate: SetupGate, token: SecretStr) -> None:
    if not gate.accepts(token.get_secret_value()):
        raise SetupError(
            "setup_link_invalid",
            "This setup link is invalid or expired. Restart the app on its computer and use the new owner setup link.",
            403,
        )


@router.post(
    "/setup",
    response_model=SessionStatus,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def create_first_administrator(
    body: SetupRequest, request: Request, response: Response
) -> SessionStatus:
    secret = require_secret()
    if not origin_allowed(request):
        raise HTTPException(403, "Origin not allowed.")
    if not login_csrf_valid(request, secret):
        raise HTTPException(403, "CSRF validation failed.")
    retry_after = auth.register_login_attempt("setup:" + client_key(request))
    if retry_after is not None:
        raise SetupError(
            "setup_rate_limited",
            "Too many setup attempts. Wait before trying again.",
            429,
            max(1, math.ceil(retry_after)),
        )
    if os.getenv("APP_MODE", "private") == "demo":
        raise SetupError(
            "setup_unavailable",
            "Account setup is unavailable in the public demo. Start a private app.",
            403,
        )
    gate = setup_gate(request)
    with Session(engine_for(request)) as db:
        require_unclaimed(db)
    if not gate.configured():
        raise SetupError(
            "setup_unavailable",
            "No active owner setup link is available. Restart the app on its computer to get a new link.",
            403,
        )
    require_setup_token(gate, body.setup_token)
    password = body.password.get_secret_value()
    # Both values were supplied in this request; neither is a hidden server
    # secret. Compare Unicode directly before validation, without unsafe encoding.
    if password != body.password_confirmation.get_secret_value():
        raise SetupError(
            "password_mismatch",
            "The passwords do not match. Enter the same password in both fields.",
            422,
        )
    try:
        name = auth.validate_admin_credentials(body.login_name, password)
    except ValueError as error:
        # The validator emits fixed policy messages, never supplied values.
        raise SetupError("invalid_credentials", str(error), 422) from None
    password_hash = auth.hash_password(password)  # No write transaction is held while hashing.
    with Session(engine_for(request)) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        require_unclaimed(db)
        require_setup_token(gate, body.setup_token)
        try:
            auth.validate_admin_credentials(name, password)
        except ValueError as error:
            raise SetupError("invalid_credentials", str(error), 422) from None
        admin = Administrator(
            login_name=name,
            password_hash=password_hash,
            local_only_password=len(password) < auth.MIN_ADMIN_PASSWORD_LENGTH,
        )
        db.add(admin)
        db.flush()
        row, token = auth.create_device_session(db, admin)
        csrf = row.csrf_token
        max_age = max(1, int((row.expires_at - auth.utcnow()).total_seconds()))
        db.commit()
    gate.consume()
    set_session_cookie(response, token, max_age)
    response.delete_cookie(ANON_CSRF_COOKIE, path="/")
    return SessionStatus(authenticated=True, role="adult", login_name=name, csrf_token=csrf)
