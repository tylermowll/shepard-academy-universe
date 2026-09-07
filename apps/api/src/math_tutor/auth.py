"""Adult authentication primitives for T02.

Passwords use Argon2id via the maintained ``argon2-cffi`` implementation.
Browser sessions are opaque random tokens: only their SHA-256 hash is
persisted, each session carries its own CSRF token, and expiry/revocation
is enforced on every lookup. Anonymous CSRF bootstrap tokens are
HMAC-signed with the session secret so login CSRF needs no server state.

This module owns credential and session rules. HTTP translation (cookies,
headers, status codes) lives in ``math_tutor.api.auth``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from math_tutor.adapters.db.models import Administrator, DeviceSession

#: How long a browser session stays valid after login.
SESSION_LIFETIME = timedelta(hours=24)

#: Anonymous (pre-login) CSRF bootstrap tokens live one hour.
ANON_CSRF_LIFETIME_SECONDS = 3600

#: Minimum administrator password accepted by the bootstrap CLI.
MIN_ADMIN_PASSWORD_LENGTH = 12
MAX_ADMIN_PASSWORD_LENGTH = 256

#: Maximum administrator login name length (matches the column width).
MAX_LOGIN_NAME_LENGTH = 64

#: Login attempts allowed per client address before temporary rejection.
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60.0
MAX_LOGIN_RATE_KEYS = 4096

_password_hasher = PasswordHasher()
# Unknown users perform the same expensive verification as known users.
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Hash a password with Argon2id; the result embeds algorithm and salt."""

    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return True only when the password matches an Argon2id hash."""

    try:
        return _password_hasher.verify(password_hash, password)
    except VerificationError, InvalidHash:
        return False


def new_opaque_token() -> str:
    """Return a fresh cookie-safe opaque session token."""

    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """Return the SHA-256 hex digest persisted for an opaque token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    """Return a fresh per-session CSRF token."""

    return secrets.token_urlsafe(32)


def sign_anon_csrf(nonce: str, secret: str) -> str:
    """Bind an anonymous CSRF nonce to this server's session secret."""

    payload = f"{int(time.time())}.{nonce}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return f"{payload}.{signature.hexdigest()}"


def verify_anon_csrf(token: str, secret: str) -> bool:
    """Return True only for a token this server signed with this secret."""

    if not token.isascii() or len(token) > 256:
        return False
    parts = token.split(".")
    if len(parts) != 3 or not parts[1]:
        return False
    issued, nonce, signature = parts
    try:
        age = time.time() - int(issued)
    except ValueError:
        return False
    if not 0 <= age < ANON_CSRF_LIFETIME_SECONDS:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), f"{issued}.{nonce}".encode("ascii"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def utcnow() -> datetime:
    """Return the current aware UTC time."""

    return datetime.now(UTC)


def normalize_login_name(login_name: str) -> str:
    """Strip surrounding whitespace; matching stays case-sensitive."""

    return login_name.strip()


def create_or_reset_admin(db: Session, login_name: str, password: str) -> Administrator:
    """Create an administrator, or reset the password when the name exists.

    Raises ``ValueError`` for an empty/oversized login name or a password
    shorter than :data:`MIN_ADMIN_PASSWORD_LENGTH`. Callers must obtain the
    password interactively (never from argv or logs).
    """

    name = normalize_login_name(login_name)
    if not name or len(name) > MAX_LOGIN_NAME_LENGTH:
        raise ValueError("Login name must be 1-64 characters.")
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_ADMIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_ADMIN_PASSWORD_LENGTH} characters.")
    # Do expensive hashing before starting a database transaction.
    password_hash = hash_password(password)
    if not db.in_transaction():
        db.connection(execution_options={"sqlite_begin_immediate": True})
    existing = db.scalar(select(Administrator).where(Administrator.login_name == name))
    if existing is not None:
        existing.password_hash = password_hash
        existing.updated_at = utcnow()
        db.execute(
            update(DeviceSession)
            .where(
                DeviceSession.administrator_id == existing.id, DeviceSession.revoked_at.is_(None)
            )
            .values(revoked_at=utcnow())
        )
        db.flush()
        return existing
    admin = Administrator(
        login_name=name,
        password_hash=password_hash,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(admin)
    db.flush()
    return admin


def authenticate_admin(db: Session, login_name: str, password: str) -> Administrator | None:
    """Return the administrator for valid credentials, else None.

    Unknown names and wrong passwords share this outcome so callers emit one
    identical 401 without distinguishing the failure.
    """

    name = normalize_login_name(login_name)
    admin = db.scalar(select(Administrator).where(Administrator.login_name == name))
    valid = verify_password(admin.password_hash if admin else _dummy_password_hash, password)
    if admin is None or not valid:
        return None
    return admin


def create_device_session(db: Session, admin: Administrator) -> tuple[DeviceSession, str]:
    """Persist an adult session row and return it with its opaque token."""

    token = new_opaque_token()
    now = utcnow()
    row = DeviceSession(
        token_hash=hash_opaque_token(token),
        role="adult",
        administrator_id=admin.id,
        learner_id=None,
        csrf_token=new_csrf_token(),
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
        revoked_at=None,
    )
    db.add(row)
    db.flush()
    return row, token


def get_valid_session(db: Session, token: str) -> DeviceSession | None:
    """Return the live session for an opaque token, else None.

    Expired and revoked rows are never returned; expiry is evaluated against
    aware UTC now on every lookup.
    """

    row = db.scalar(
        select(DeviceSession).where(DeviceSession.token_hash == hash_opaque_token(token))
    )
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at <= utcnow():
        return None
    return row


def revoke_session(db: Session, row: DeviceSession) -> None:
    """Mark a session revoked so its token stops authenticating immediately."""

    row.revoked_at = utcnow()
    db.flush()


_login_attempts: dict[str, tuple[float, int]] = {}
_login_attempts_lock = Lock()


def register_login_attempt(key: str, limit: int | None = None) -> float | None:
    """Record a login attempt; return retry-after seconds when over budget.

    At most :data:`LOGIN_RATE_LIMIT` attempts per
    :data:`LOGIN_RATE_WINDOW_SECONDS` are accepted per key (client address).
    Fixed windows, a bounded key count, and a lock bound memory and concurrent
    admission. This process-local limiter matches the one-API-process contract.
    """

    now = time.monotonic()
    with _login_attempts_lock:
        expired = [address for address, (end, _) in _login_attempts.items() if end <= now]
        for address in expired:
            del _login_attempts[address]
        if key not in _login_attempts and len(_login_attempts) >= MAX_LOGIN_RATE_KEYS:
            return min(end for end, _ in _login_attempts.values()) - now
        end, count = _login_attempts.get(key, (now + LOGIN_RATE_WINDOW_SECONDS, 0))
        if count >= (LOGIN_RATE_LIMIT if limit is None else limit):
            return end - now
        _login_attempts[key] = (end, count + 1)
        return None


def clear_login_rate_limit() -> None:
    """Forget all recorded login attempts (tests only)."""

    with _login_attempts_lock:
        _login_attempts.clear()
