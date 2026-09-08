"""Adult session endpoints for T02.

Routes (all under ``/api/v1/auth``):

* ``GET /session`` — minimal status plus CSRF bootstrap; never a learner list.
* ``POST /login`` — opaque session cookie on valid credentials.
* ``POST /logout`` — immediate revocation of the presenting session.

State-changing requests require the ``X-CSRF-Token`` header and a passing
``Origin`` check. Cookies are ``HttpOnly`` (session) and ``SameSite=Lax``;
``Secure`` follows the configured public origin so loopback development over
plain HTTP keeps working while HTTPS deployments set it. Login attempts are
rate-limited per client address. A missing or placeholder ``SESSION_SECRET``
fails closed with 500; the liveness probe stays exempt.
"""

from __future__ import annotations

import hmac
import math
import secrets
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from math_tutor import auth as auth_service
from math_tutor import settings
from math_tutor.adapters.db.models import Administrator, Learner

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SESSION_COOKIE = "mt_session"
ANON_CSRF_COOKIE = "mt_csrf_anon"
CSRF_HEADER = "x-csrf-token"

_NOT_CONFIGURED = "Server authentication is not configured."
_BAD_CREDENTIALS = "Invalid login name or password."
_NOT_AUTHENTICATED = "Not authenticated."
_CSRF_FAILED = "CSRF validation failed."
_ORIGIN_REJECTED = "Origin not allowed."
_RATE_LIMITED = "Too many login attempts. Try again later."


class LoginRequest(BaseModel):
    """Credentials for the administrator or one learner account."""

    model_config = ConfigDict(frozen=True)

    login_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=auth_service.MAX_ADMIN_PASSWORD_LENGTH)


class SessionStatus(BaseModel):
    """Minimal session state plus the CSRF token the client must echo.

    Never carries password hashes, opaque token hashes, or learner lists.
    """

    model_config = ConfigDict(frozen=True)

    authenticated: bool
    role: Literal["adult", "learner"] | None = None
    login_name: str | None = None
    learner_id: UUID | None = None
    csrf_token: str
    setup_required: bool = False


class LogoutResponse(BaseModel):
    """Result of revoking the presenting session."""

    model_config = ConfigDict(frozen=True)

    authenticated: bool = False


def require_secret() -> str:
    """Return the session secret or fail closed when it is unconfigured."""

    try:
        settings.app_public_origin()
        return settings.session_secret()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_NOT_CONFIGURED,
        ) from None


def secure_cookies() -> bool:
    """Use the Secure cookie flag outside loopback development."""

    return urlsplit(settings.app_public_origin()).scheme == "https"


def origin_allowed(request: Request) -> bool:
    """Accept missing Origin (non-browser clients); otherwise same-origin only.

    Host must match configured authority. An explicit Origin must match the
    full configured origin, including scheme and port; caller-controlled Host
    and forwarding headers never expand the allowlist.
    """

    public = settings.app_public_origin()
    return request.headers.get("host", "").lower() == urlsplit(public).netloc and (
        request.headers.get("origin") in (None, public)
    )


def csrf_matches(presented: str | None, expected: str) -> bool:
    """Reject malformed headers without compare_digest raising on Unicode."""

    return (
        presented is not None and presented.isascii() and hmac.compare_digest(presented, expected)
    )


def engine_for(request: Request) -> Engine:
    """Return the application's database engine."""

    return cast(Engine, request.app.state.engine)


def client_key(request: Request) -> str:
    """Return the rate-limit key for this caller."""

    if request.client is not None:
        return request.client.host
    return "unknown"


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    """Store the opaque session token with the T02 cookie contract."""

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure_cookies(),
    )


def set_anon_csrf_cookie(response: Response, token: str) -> None:
    """Store the anonymous bootstrap token for double-submit login CSRF."""

    response.set_cookie(
        ANON_CSRF_COOKIE,
        token,
        max_age=auth_service.ANON_CSRF_LIFETIME_SECONDS,
        path="/",
        httponly=False,
        samesite="lax",
        secure=secure_cookies(),
    )


def mint_anon_csrf(secret: str) -> str:
    """Return a fresh anonymous bootstrap token signed with the secret."""

    return auth_service.sign_anon_csrf(secrets.token_urlsafe(24), secret)


def login_csrf_valid(request: Request, secret: str) -> bool:
    """Bind reauthentication to its current session, or login to its bootstrap."""

    presented = request.headers.get(CSRF_HEADER)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with Session(engine_for(request)) as db:
            row = auth_service.get_valid_session(db, token)
            if row is not None:
                return csrf_matches(presented, row.csrf_token)
    bootstrap = request.cookies.get(ANON_CSRF_COOKIE)
    return (
        bootstrap is not None
        and bootstrap.isascii()
        and csrf_matches(presented, bootstrap)
        and auth_service.verify_anon_csrf(bootstrap, secret)
    )


@router.get(
    "/session",
    response_model=SessionStatus,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def get_session(request: Request, response: Response) -> SessionStatus:
    """Report minimal session state and bootstrap a CSRF token."""

    secret = require_secret()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with Session(engine_for(request)) as db:
            row = auth_service.get_valid_session(db, token)
            if row is not None:
                login_name = row.administrator.login_name if row.administrator is not None else None
                if row.learner_id:
                    learner = db.get(Learner, row.learner_id)
                    login_name = learner.alias if learner else None
                return SessionStatus(
                    authenticated=True,
                    role=cast(Literal["adult", "learner"], row.role),
                    login_name=login_name,
                    learner_id=row.learner_id,
                    csrf_token=row.csrf_token,
                )
        response.delete_cookie(SESSION_COOKIE, path="/")
    anon = mint_anon_csrf(secret)
    set_anon_csrf_cookie(response, anon)
    with Session(engine_for(request)) as db:
        needs_setup = auth_service.setup_required(db)
    return SessionStatus(authenticated=False, csrf_token=anon, setup_required=needs_setup)


@router.post(
    "/login",
    response_model=SessionStatus,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def login(credentials: LoginRequest, request: Request, response: Response) -> SessionStatus:
    """Authenticate one account and recheck its credentials before issuing a cookie."""

    secret = require_secret()
    if not origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ORIGIN_REJECTED)
    if not login_csrf_valid(request, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_CSRF_FAILED)
    retry_after = auth_service.register_login_attempt(client_key(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_RATE_LIMITED,
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
    with Session(engine_for(request)) as db:
        account: Administrator | Learner | None = auth_service.authenticate_admin(
            db, credentials.login_name, credentials.password
        )
        if account is None:
            account = auth_service.authenticate_learner(
                db, credentials.login_name, credentials.password
            )
        if account is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS)
        if account.local_only_password and not auth_service.local_passwords_allowed():
            raise HTTPException(
                403,
                "This account has a local-only password. Set at least 12 characters on the app computer before using HTTPS or phone access. The administrator can reset learner passwords in Learners; use make admin for the administrator account.",
            )
        # End the read snapshot after password verification. The short write
        # transaction rechecks the hash so a concurrent reset cannot be bypassed.
        account_id, password_hash = account.id, account.password_hash
        is_administrator = isinstance(account, Administrator)
        db.rollback()
        db.connection(execution_options={"sqlite_begin_immediate": True})
        account = (
            db.get(Administrator, account_id, populate_existing=True)
            if is_administrator
            else db.get(Learner, account_id, populate_existing=True)
        )
        if (
            account is None
            or account.password_hash != password_hash
            or (
                isinstance(account, Learner)
                and (not account.enabled or account.deleted_at is not None)
            )
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS)
        if account.local_only_password and not auth_service.local_passwords_allowed():
            raise HTTPException(
                403,
                "This account needs a password reset on the app computer before network access.",
            )
        previous = request.cookies.get(SESSION_COOKIE)
        if previous:
            old_session = auth_service.get_valid_session(db, previous)
            if old_session is not None:
                auth_service.revoke_session(db, old_session)
        if isinstance(account, Administrator):
            row, token = auth_service.create_device_session(db, account)
            name = account.login_name
        else:
            row, token = auth_service.create_learner_session(db, account)
            name = account.alias
        role = cast(Literal["adult", "learner"], row.role)
        learner_id = row.learner_id
        csrf = row.csrf_token
        max_age = max(1, int((row.expires_at - auth_service.utcnow()).total_seconds()))
        db.commit()
    set_session_cookie(response, token, max_age)
    response.delete_cookie(ANON_CSRF_COOKIE, path="/")
    return SessionStatus(
        authenticated=True, role=role, login_name=name, learner_id=learner_id, csrf_token=csrf
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request, response: Response) -> LogoutResponse:
    """Revoke the presenting session and clear its cookie."""

    require_secret()
    if not origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ORIGIN_REJECTED)
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_NOT_AUTHENTICATED)
    with Session(engine_for(request)) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        row = auth_service.get_valid_session(db, token)
        if row is None:
            response.delete_cookie(SESSION_COOKIE, path="/")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_NOT_AUTHENTICATED)
        presented = request.headers.get(CSRF_HEADER)
        if not csrf_matches(presented, row.csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_CSRF_FAILED)
        auth_service.revoke_session(db, row)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return LogoutResponse()
