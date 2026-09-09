"""Ephemeral local-owner authority, never a public token-issuing service."""

import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock

from math_tutor.auth import hash_opaque_token

SETUP_TOKEN_ENV_VAR = "SHEPARD_SETUP_TOKEN"
SETUP_LIFETIME_SECONDS = 30 * 60
SETUP_SESSION_LIFETIME_SECONDS = 8 * 60 * 60


def sign_setup_session(secret: str, origin: str) -> str:
    """Issue permission for setup only, independently of the launcher's lifetime."""
    payload = f"{int(time.time())}.{secrets.token_urlsafe(32)}"
    signature = hmac.new(secret.encode(), f"first-admin:{origin}:{payload}".encode(), "sha256")
    return f"{payload}.{signature.hexdigest()}"


def valid_setup_session(token: str, secret: str, origin: str) -> bool:
    if re.fullmatch(r"[0-9]{1,12}\.[A-Za-z0-9_-]{43}\.[a-f0-9]{64}", token) is None:
        return False
    payload, signature = token.rsplit(".", 1)
    age = time.time() - int(payload.split(".", 1)[0])
    expected = hmac.new(secret.encode(), f"first-admin:{origin}:{payload}".encode(), "sha256")
    return 0 <= age < SETUP_SESSION_LIFETIME_SECONDS and hmac.compare_digest(
        signature, expected.hexdigest()
    )


@dataclass
class SetupError(Exception):
    code: str
    safe_message: str
    status_code: int
    retry_after: int | None = None


@dataclass
class SetupGate:
    """Retain only the owner-link digest and monotonic expiry in API memory.

    The exchange consumes the link under the database write lock. Its signed
    browser cookie remains usable if account creation rolls back or the API
    restarts. The database first-admin check closes setup after a committed claim.
    """

    _token_hash: str | None = field(default=None, repr=False)
    _expires_at: float = field(default=0, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def from_environment(cls) -> SetupGate:
        token = os.environ.pop(SETUP_TOKEN_ENV_VAR, None)
        if (
            os.getenv("APP_MODE", "private") == "demo"
            or token is None
            or re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) is None
        ):
            return cls()
        return cls(hash_opaque_token(token), time.monotonic() + SETUP_LIFETIME_SECONDS)

    def available(self) -> bool:
        with self._lock:
            return self._token_hash is not None and time.monotonic() < self._expires_at

    def accepts(self, token: str) -> bool:
        with self._lock:
            return (
                self._token_hash is not None
                and time.monotonic() < self._expires_at
                and re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) is not None
                and hmac.compare_digest(self._token_hash, hash_opaque_token(token))
            )

    def consume(self) -> None:
        with self._lock:
            self._token_hash = None

    def renew(self) -> str:
        """Issue only through the local owner channel after checking the database."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._token_hash = hash_opaque_token(token)
            self._expires_at = time.monotonic() + SETUP_LIFETIME_SECONDS
        return token
